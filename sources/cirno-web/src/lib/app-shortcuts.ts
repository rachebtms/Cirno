type NavigatorWithUserAgentData = Navigator & {
  userAgentData?: { platform?: string };
};

export function isApplePlatform(): boolean {
  if (typeof navigator === "undefined") return false;
  const platform = navigator.platform || "";
  const userAgentPlatform =
    (navigator as NavigatorWithUserAgentData).userAgentData?.platform || "";
  return /mac|iphone|ipad|ipod/i.test(`${platform} ${userAgentPlatform}`);
}

const APP_SHORTCUTS = {
  newChat: { key: "O", shift: true },
  search: { key: "K", shift: false },
  apps: { key: "1", shift: true },
  skills: { key: "2", shift: true },
  automations: { key: "3", shift: true },
  channels: { key: "4", shift: true },
  settings: { key: ",", shift: false },
} as const;

export type AppShortcut = keyof typeof APP_SHORTCUTS;

export function appShortcutLabel(action: AppShortcut, apple: boolean): string {
  const { key, shift } = APP_SHORTCUTS[action];
  return apple
    ? `⌘${shift ? "⇧" : ""}${key}`
    : `Ctrl+${shift ? "Shift+" : ""}${key}`;
}

export function matchAppShortcut(
  event: KeyboardEvent,
): AppShortcut | undefined {
  if (
    event.defaultPrevented ||
    event.repeat ||
    event.isComposing ||
    event.altKey ||
    !(event.metaKey || event.ctrlKey)
  )
    return undefined;
  return (Object.keys(APP_SHORTCUTS) as AppShortcut[]).find((action) => {
    const { key, shift } = APP_SHORTCUTS[action];
    return (
      event.shiftKey === shift &&
      (event.key.toUpperCase() === key ||
        (/^[0-9]$/.test(key) && event.code === `Digit${key}`))
    );
  });
}
