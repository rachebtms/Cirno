import { useSyncExternalStore } from "react";
import {
  subscribePreferences,
  readOwnerPreferences,
  readPreferenceStatus,
  readThemes,
} from "@/features/preferences/store";
export function usePreferences() {
  return useSyncExternalStore(subscribePreferences, readOwnerPreferences);
}
export function usePreferenceStatus() {
  return useSyncExternalStore(subscribePreferences, readPreferenceStatus);
}
export function useThemes() {
  return useSyncExternalStore(subscribePreferences, readThemes);
}
