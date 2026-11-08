import {
  connectPreferences,
  DEFAULT_OWNER_PREFERENCES,
  receivePreferences,
  SNOW_THEME,
  type OwnerPreferences,
  type PreferencesSnapshot,
} from "@/features/preferences/store";

/** Simulated server state for component fixtures in one browser context. */
export const PREVIEW_PREFERENCES_KEY = "cirno-browser-fixture.owner-preferences";

export function installPreviewPreferences(initial: Partial<OwnerPreferences> = {}) {
  const saved = localStorage.getItem(PREVIEW_PREFERENCES_KEY);
  const stored = saved ? JSON.parse(saved) as Partial<PreferencesSnapshot> : null;
  let snapshot: PreferencesSnapshot = {
    revision: stored?.revision ?? 0,
    values: { ...DEFAULT_OWNER_PREFERENCES, ...initial, ...stored?.values },
    themes: stored?.themes ?? [SNOW_THEME],
  };
  localStorage.setItem(PREVIEW_PREFERENCES_KEY, JSON.stringify(snapshot));
  window.addEventListener("storage", event => {
    if (event.key !== PREVIEW_PREFERENCES_KEY || !event.newValue) return;
    snapshot = JSON.parse(event.newValue) as PreferencesSnapshot;
    receivePreferences(snapshot);
  });
  receivePreferences(snapshot);
  connectPreferences({
    onPreferencesUpdate: () => () => {},
    onStatus: () => () => {},
    requestMutation: async (method, args) => {
      if (method !== "preferences.read" && method !== "preferences.update") {
        throw new Error(`Unsupported preview preference action: ${method}`);
      }
      if (method === "preferences.update") {
        snapshot = { ...snapshot, revision: snapshot.revision + 1, values: { ...snapshot.values, ...args.patch as Partial<OwnerPreferences> } };
        localStorage.setItem(PREVIEW_PREFERENCES_KEY, JSON.stringify(snapshot));
      }
      return snapshot;
    },
  });
}
