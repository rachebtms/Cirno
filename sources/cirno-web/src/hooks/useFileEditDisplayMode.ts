import { usePreferences } from "@/hooks/usePreferences";
import type { FileEditDisplayMode } from "@/features/preferences/store";

export function useFileEditDisplayMode(): FileEditDisplayMode {
  return usePreferences().fileEditDisplayMode;
}
