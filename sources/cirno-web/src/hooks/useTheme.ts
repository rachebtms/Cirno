import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useLayoutEffect,
  type ReactNode,
} from "react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { usePreferences, useThemes } from "@/hooks/usePreferences";
import {
  patchPreferences,
  SNOW_THEME,
  type ThemeMode,
} from "@/features/preferences/store";
import { applyPalette } from "@/features/preferences/palette";
export type ThemePreference = ThemeMode;
type Theme = "light" | "dark";
const ThemeContext = createContext<Theme>("light");
export function useTheme() {
  const preferences = usePreferences();
  const builtins = useThemes();
  const systemDark = useMediaQuery("(prefers-color-scheme: dark)");
  const theme: Theme =
    preferences.themeMode === "system"
      ? systemDark
        ? "dark"
        : "light"
      : preferences.themeMode;
  const selected =
    [...builtins, ...preferences.customThemes].find(
      (theme) => theme.id === preferences.themeId,
    ) ?? SNOW_THEME;
  useLayoutEffect(
    () => applyPalette(selected[theme], theme === "dark"),
    [selected, theme],
  );
  const setTheme = useCallback(
    (themeMode: ThemePreference) => patchPreferences({ themeMode }),
    [],
  );
  const toggle = useCallback(
    () => setTheme(theme === "dark" ? "light" : "dark"),
    [theme, setTheme],
  );
  return { theme, preference: preferences.themeMode, setTheme, toggle };
}
export function ThemeProvider({
  theme,
  children,
}: {
  theme: Theme;
  children: ReactNode;
}) {
  return createElement(ThemeContext.Provider, { value: theme }, children);
}
export function useThemeValue(): Theme {
  return useContext(ThemeContext);
}
