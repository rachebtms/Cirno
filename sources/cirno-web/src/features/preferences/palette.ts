import type { Palette } from "./contracts";
function channels(hex: string) {
  return [1, 3, 5].map(
    (offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255,
  );
}
export function luminance(hex: string) {
  const linear = channels(hex).map((value) =>
    value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
  );
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
}
export function contrast(first: string, second: string) {
  const values = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}
function hsl(hex: string) {
  const [r, g, b] = channels(hex),
    max = Math.max(r, g, b),
    min = Math.min(r, g, b);
  const delta = max - min,
    light = (max + min) / 2;
  let hue = 0;
  if (delta) {
    if (max === r) hue = ((g - b) / delta) % 6;
    else if (max === g) hue = (b - r) / delta + 2;
    else hue = (r - g) / delta + 4;
  }
  return `${(hue * 60 + 360) % 360} ${delta ? (delta / (1 - Math.abs(2 * light - 1))) * 100 : 0}% ${light * 100}%`;
}
export function applyPalette(palette: Palette, dark: boolean) {
  const root = document.documentElement;
  root.classList.toggle("dark", dark);
  root.style.colorScheme = dark ? "dark" : "light";
  const foreground =
    contrast(palette.accent, "#ffffff") >= contrast(palette.accent, "#10202c")
      ? "#ffffff"
      : "#10202c";
  const groups: Record<string, string[]> = {
    background: ["background", "settings-canvas"],
    surface: ["sidebar", "settings-surface", "muted", "secondary", "accent"],
    panel: ["card", "popover", "sidebar-accent", "sidebar-selected"],
    text: [
      "foreground",
      "card-foreground",
      "popover-foreground",
      "secondary-foreground",
      "accent-foreground",
      "sidebar-foreground",
      "sidebar-content",
      "sidebar-accent-foreground",
    ],
    muted: ["muted-foreground", "sidebar-muted-foreground"],
    accent: ["primary", "ring", "sidebar-primary", "sidebar-ring"],
    border: ["border", "input", "sidebar-border"],
  };
  for (const [key, names] of Object.entries(groups))
    for (const name of names)
      root.style.setProperty(`--cirno-${name}`, hsl(palette[key as keyof Palette]));
  root.style.setProperty("--cirno-primary-foreground", hsl(foreground));
  root.style.setProperty("--cirno-sidebar-primary-foreground", hsl(foreground));
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", palette.background);
}
