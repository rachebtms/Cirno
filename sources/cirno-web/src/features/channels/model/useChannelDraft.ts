import { useCallback, useState } from "react";
import type {
  ChannelConfigField,
  ChannelProviderPreset,
} from "@/channel-plugins/catalog";
import {
  defaultChannelFieldValues,
  channelValuesForSubmit,
} from "./fieldValues";
type Changes = Record<string, string | null>;
export function useChannelDraft(
  owner: unknown,
  fields: ChannelConfigField[],
  saved?: Record<string, string>,
) {
  const [state, setState] = useState({
    owner,
    changes: {} as Changes,
    revision: 0,
    visible: {} as Record<string, boolean>,
  });
  const current =
    state.owner === owner
      ? state
      : {
          owner,
          changes: {} as Changes,
          revision: 0,
          visible: {} as Record<string, boolean>,
        };
  const values = {
    ...defaultChannelFieldValues(fields, saved),
    ...Object.fromEntries(
      Object.entries(current.changes).map(([key, value]) => [key, value ?? ""]),
    ),
  };
  const touched = new Set(Object.keys(current.changes)),
    cleared = new Set(
      Object.keys(current.changes).filter(
        (key) => current.changes[key] === null,
      ),
    );
  const change = useCallback(
    (key: string, value: string | null) =>
      setState((previous) => ({
        owner,
        visible: previous.owner === owner ? previous.visible : {},
        revision: previous.owner === owner ? previous.revision + 1 : 1,
        changes: {
          ...(previous.owner === owner ? previous.changes : {}),
          [key]: value,
        },
      })),
    [owner],
  );
  const ack = useCallback(
    (snapshot: Changes) =>
      setState((previous) => {
        if (previous.owner !== owner) return previous;
        const changes = { ...previous.changes };
        for (const [key, value] of Object.entries(snapshot))
          if (changes[key] === value) delete changes[key];
        return { ...previous, changes };
      }),
    [owner],
  );
  return {
    values,
    revision: current.revision,
    touched,
    cleared,
    snapshot: current.changes,
    dirty: touched.size > 0,
    visible: current.visible,
    payload: channelValuesForSubmit(fields, values, touched, cleared),
    change,
    ack,
    toggleSecret: (key: string) =>
      setState((previous) => ({
        owner,
        changes: previous.owner === owner ? previous.changes : {},
        revision: previous.owner === owner ? previous.revision : 0,
        visible: {
          ...(previous.owner === owner ? previous.visible : {}),
          [key]: !current.visible[key],
        },
      })),
    clearSecret: (key: string, clear: boolean) => {
      if (clear) change(key, null);
      else
        setState((previous) => {
          if (previous.owner !== owner) return previous;
          const changes = { ...previous.changes };
          delete changes[key];
          return { ...previous, changes, revision: previous.revision + 1 };
        });
    },
    applyPreset: (preset: ChannelProviderPreset) =>
      setState((previous) => ({
        owner,
        visible: previous.owner === owner ? previous.visible : {},
        revision: previous.owner === owner ? previous.revision + 1 : 1,
        changes: {
          ...(previous.owner === owner ? previous.changes : {}),
          ...Object.fromEntries(
            Object.entries(preset.values).filter(
              ([key]) => !(values[key] ?? "").trim(),
            ),
          ),
        },
      })),
  };
}
export type ChannelDraft = ReturnType<typeof useChannelDraft>;
