import type { CirnoClient } from "@/lib/cirno-client";
import type { Dispatch, SetStateAction } from "react";
import {
  DEFAULT_OWNER_PREFERENCES,
  SNOW_THEME,
  type DisplayPreferences,
  type OwnerPreferences,
  type PreferencesSnapshot,
  type ThemePair,
} from "./contracts";
export * from "./contracts";

type Save = (
  patch: Partial<OwnerPreferences>,
  revision?: number,
) => Promise<PreferencesSnapshot>;

export type PreferencesConnection = Pick<CirnoClient, "onPreferencesUpdate" | "onStatus"> & {
  requestMutation: (action: string, payload: Record<string, unknown>) => Promise<PreferencesSnapshot>;
};
let server: PreferencesSnapshot = {
  revision: 0,
  values: DEFAULT_OWNER_PREFERENCES,
  themes: [SNOW_THEME],
};
let current = server.values;
let status = { saving: false, error: "" };
interface PendingPreference {
  patch: Partial<OwnerPreferences>;
  themeBase?: string;
  acknowledge: (saved: boolean) => void;
}
let pending: PendingPreference[] = [];
let sink: Save | null = null;
let draining = false;
let syncEpoch = 0;
const listeners = new Set<() => void>();
export const subscribePreferences = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
export const readOwnerPreferences = () => current;
export const readPreferences = (): DisplayPreferences => current;
export const readPreferenceStatus = () => status;
export const readThemes = () => server.themes;
function themeSignature(themes: readonly ThemePair[]) {
  return JSON.stringify(themes.map(theme => [
    theme.id, theme.name,
    ...[theme.light, theme.dark].map(palette => Object.entries(palette).sort(([a], [b]) => a.localeCompare(b))),
  ]));
}
function publish() {
  current = pending.reduce<OwnerPreferences>(
    (values, entry) => ({ ...values, ...entry.patch }),
    server.values,
  );
  for (const listener of listeners) listener();
}
export function receivePreferences(snapshot: PreferencesSnapshot | undefined) {
  if (!snapshot || snapshot.revision < server.revision) return;
  server = snapshot;
  publish();
}
async function drain() {
  if (draining || !sink) return;
  draining = true;
  const epoch = syncEpoch;
  try {
    while (pending.length && sink) {
      status = { saving: true, error: status.error };
      publish();
      const entry = pending[0];
      const patch = entry.patch;
      try {
        if (entry.themeBase !== undefined && entry.themeBase !== themeSignature(server.values.customThemes)) {
          throw new Error("Preferences changed on another device. Reload before saving this theme.");
        }
        const saved = await sink(
          patch,
          entry.themeBase !== undefined ? server.revision : undefined,
        );
        if (epoch !== syncEpoch) return;
        pending.shift();
        entry.acknowledge(true);
        if (saved.revision >= server.revision) server = saved;
        status = { saving: pending.length > 0, error: status.error };
      } catch (error) {
        if (epoch !== syncEpoch) return;
        pending.shift();
        entry.acknowledge(false);
        status = {
          saving: false,
          error: error instanceof Error ? error.message : String(error),
        };
        publish();
        continue;
      }
      publish();
    }
  } finally {
    draining = false;
    if (epoch !== syncEpoch) void drain();
  }
}
export function patchPreferences(
  patch: Partial<OwnerPreferences>,
  options?: { customThemesBase?: readonly ThemePair[] },
): Promise<boolean> {
  let acknowledge!: (saved: boolean) => void;
  const receipt = new Promise<boolean>(resolve => { acknowledge = resolve; });
  pending.push({
    patch: structuredClone(patch),
    ...(patch.customThemes !== undefined ? { themeBase: themeSignature(options?.customThemesBase ?? current.customThemes) } : {}),
    acknowledge,
  });
  status = { ...status, error: "" };
  publish();
  void drain();
  return receipt;
}
export const writePreferences: Dispatch<SetStateAction<DisplayPreferences>> = (
  update,
) => {
  const next = typeof update === "function" ? update(current) : update;
  const patch = Object.fromEntries(
    Object.entries(next).filter(
      ([key, value]) =>
        JSON.stringify(value) !==
        JSON.stringify(current[key as keyof OwnerPreferences]),
    ),
  ) as Partial<OwnerPreferences>;
  if (Object.keys(patch).length) patchPreferences(patch);
};
export function connectPreferences(client: PreferencesConnection) {
  let connected = true;
  const epoch = syncEpoch;
  const save: Save = (patch, expected_revision) =>
    client.requestMutation("preferences.update", { patch, expected_revision });
  sink = save;
  const stopUpdates = client.onPreferencesUpdate((snapshot) => {
    if (connected && epoch === syncEpoch) receivePreferences(snapshot);
  });
  const stopStatus = client.onStatus((connection) => {
    if (connection === "open")
      void client
        .requestMutation("preferences.read", {
          operation: "read",
        })
        .then((snapshot) => {
          if (connected && epoch === syncEpoch) receivePreferences(snapshot);
        })
        .catch((error: Error) => {
          if (connected && epoch === syncEpoch) {
            status = { saving: false, error: error.message };
            publish();
          }
        });
  });
  void drain();
  return () => {
    connected = false;
    stopUpdates();
    stopStatus();
    if (sink === save) sink = null;
  };
}

export function clearOwnerPreferences() {
  syncEpoch += 1;
  for (const entry of pending) entry.acknowledge(false);
  server = {
    revision: 0,
    values: DEFAULT_OWNER_PREFERENCES,
    themes: [SNOW_THEME],
  };
  pending = [];
  status = { saving: false, error: "" };
  sink = null;
  publish();
}
