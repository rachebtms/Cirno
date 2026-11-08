import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTheme } from "@/hooks/useTheme";
import { clearOwnerPreferences, DEFAULT_OWNER_PREFERENCES, receivePreferences, SNOW_THEME } from "@/features/preferences/store";

describe("paired owner themes", () => {
  let systemDark = false;
  let mediaEvents: EventTarget;
  beforeEach(() => {
    systemDark = false;
    mediaEvents = new EventTarget();
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      get matches() { return query === "(prefers-color-scheme: dark)" && systemDark; },
      addEventListener: mediaEvents.addEventListener.bind(mediaEvents),
      removeEventListener: mediaEvents.removeEventListener.bind(mediaEvents),
    })));
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.append(meta);
  });
  afterEach(() => {
    cleanup();
    clearOwnerPreferences();
    vi.unstubAllGlobals();
    document.querySelector('meta[name="theme-color"]')?.remove();
    document.documentElement.classList.remove("dark");
    document.documentElement.removeAttribute("style");
  });

  it.each(["light", "dark"] as const)("restores the owner's %s variant and browser chrome", themeMode => {
    receivePreferences({ revision: 1, values: { ...DEFAULT_OWNER_PREFERENCES, themeMode }, themes: [SNOW_THEME] });
    const { result } = renderHook(useTheme);
    expect(result.current.theme).toBe(themeMode);
    expect(document.documentElement.classList.contains("dark")).toBe(themeMode === "dark");
    expect(document.querySelector('meta[name="theme-color"]')?.getAttribute("content")).toBe(SNOW_THEME[themeMode].background);
  });

  it("follows live system changes without replacing the saved mode", () => {
    const { result } = renderHook(useTheme);
    expect(result.current.theme).toBe("light");
    act(() => { systemDark = true; mediaEvents.dispatchEvent(new Event("change")); });
    expect(result.current.theme).toBe("dark");
    expect(result.current.preference).toBe("system");
  });

  it("switches both variants while keeping the selected paired theme", () => {
    const custom = { ...SNOW_THEME, id: "custom-snow", name: "Personal snow", dark: { ...SNOW_THEME.dark, background: "#09121e" } };
    receivePreferences({ revision: 1, values: { ...DEFAULT_OWNER_PREFERENCES, themeId: custom.id, customThemes: [custom] }, themes: [SNOW_THEME] });
    const { result } = renderHook(useTheme);
    act(() => { void result.current.toggle(); });
    expect(result.current.theme).toBe("dark");
    expect(document.querySelector('meta[name="theme-color"]')?.getAttribute("content")).toBe("#09121e");
    act(() => { void result.current.toggle(); });
    expect(result.current.theme).toBe("light");
    expect(document.querySelector('meta[name="theme-color"]')?.getAttribute("content")).toBe(SNOW_THEME.light.background);
  });

  it("applies a change broadcast by another device", () => {
    const { result } = renderHook(useTheme);
    act(() => receivePreferences({ revision: 4, values: { ...DEFAULT_OWNER_PREFERENCES, themeMode: "dark" }, themes: [SNOW_THEME] }));
    expect(result.current.preference).toBe("dark");
    expect(result.current.theme).toBe("dark");
  });
});
