import { normalizeLocale } from "@/i18n/config";
import {
  connectPreferences, receivePreferences, DEFAULT_OWNER_PREFERENCES, SNOW_THEME,
  type OwnerPreferences, type PreferencesSnapshot,
} from "@/features/preferences/store";

/** Gallery view options live in its URL; they do not change the instance owner. */
export function initializeGalleryPreferences() {
  const url = new URL(window.location.href);
  const theme = url.searchParams.get("theme");
  let snapshot: PreferencesSnapshot = {
    revision: 0,
    values: {
      ...DEFAULT_OWNER_PREFERENCES,
      language: normalizeLocale(url.searchParams.get("lang") ?? navigator.language),
      themeMode: theme === "dark" || theme === "light" ? theme : "system",
    },
    themes: [SNOW_THEME],
  };
  receivePreferences(snapshot);
  connectPreferences({
    onPreferencesUpdate: () => () => {},
    onStatus: () => () => {},
    requestMutation: async (action, payload) => {
      if (action === "preferences.read") return snapshot;
      if (action !== "preferences.update") throw new Error(`Unsupported gallery action: ${action}`);
      const patch = payload.patch as Partial<OwnerPreferences>;
      snapshot = { ...snapshot, revision: snapshot.revision + 1, values: { ...snapshot.values, ...patch } };
      const next = new URL(window.location.href);
      next.searchParams.set("lang", snapshot.values.language);
      next.searchParams.set("theme", snapshot.values.themeMode);
      window.history.replaceState(window.history.state, "", next);
      return snapshot;
    },
  });
}
