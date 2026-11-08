import type { SettingsSectionKey } from "@/features/settings/SettingsView";
import { settingsSections } from "@/features/settings/modules";
import { CirnoClient } from "@/lib/cirno-client";
import type { BootstrapResponse } from "@/lib/contracts/bootstrap";
import { lazy } from "react";

export type BootState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "auth"; failed?: boolean; accountMode?: "register" | "login" }
  | {
    status: "ready";
    client: CirnoClient;
    token: string;
    tokenExpiresAt: number | null;
    modelName: string | null;
    ingressLimits: BootstrapResponse["limits"] | null;

    webuiCapabilities: string[];
    accountAuth?: boolean;
    onboardingRequired?: boolean;
  };

export function bootstrapCapabilities(boot: BootstrapResponse): string[] {
  const capabilities = boot.terminal?.webui?.capabilities;
  return Array.isArray(capabilities)
    ? capabilities.filter((entry) => typeof entry === "string")
    : [];
}


export const SESSION_UPDATES_STORAGE_KEY =
  "cirno-webui.sidebar.session-updates.v1";

export const RESTART_STARTED_KEY = "cirno-webui.restartStartedAt";

export const RESTART_ROUTE_KEY = "cirno-webui.restartRoute";

export const RESTART_ROUTE_TTL_MS = 5 * 60 * 1000;




export const TOKEN_REFRESH_MARGIN_MS = 30_000;

export const TOKEN_REFRESH_MIN_DELAY_MS = 5_000;




export type ShellView =
  | "chat"
  | "settings"
  | "apps"
  | "automations"
  | "skills"
  | "channels"
  | "inbox";

export type ShellRoute = {
  view: ShellView;
  activeKey: string | null;
  settingsSection: SettingsSectionKey;
  temporary?: boolean;
  tabId?: string;
};

export const InboxPage = lazy(() =>
  import("@/features/inbox/InboxPage").then((module) => ({
    default: module.InboxPage,
  })),
);

export const SetupFlow = lazy(() =>
  import("@/features/entry/SetupFlow").then((module) => ({
    default: module.SetupFlow,
  })),
);

export const loadThreadShell = () => import("@/components/thread/ThreadShell");

export const ThreadShell = lazy(() =>
  loadThreadShell().then((module) => ({ default: module.ThreadShell })),
);

export const loadSettingsView = () =>
  import("@/features/settings/SettingsView");

export const SettingsView = lazy(async () => {
  const module = await loadSettingsView();
  return { default: module.SettingsView };
});

export const SessionSearchDialog = lazy(async () => {
  const module = await import("@/components/SessionSearchDialog");
  return { default: module.SessionSearchDialog };
});

export const DeleteConfirm = lazy(async () => {
  const module = await import("@/components/DeleteConfirm");
  return { default: module.DeleteConfirm };
});

export const SETTINGS_SECTION_KEYS: SettingsSectionKey[] = [
  ...settingsSections.navigation.map(section => section.key), "automations", "capabilities",
];

export function isSettingsSectionKey(
  value: string | null,
): value is SettingsSectionKey {
  return SETTINGS_SECTION_KEYS.includes(value as SettingsSectionKey);
}

export function defaultShellRoute(): ShellRoute {
  return { view: "chat", activeKey: null, settingsSection: "overview" };
}

export function changesSettingsSurface(
  current: ShellRoute,
  next: ShellRoute,
): boolean {
  return (
    current.view !== "chat" &&
    (current.view !== next.view ||
      current.settingsSection !== next.settingsSection ||
      current.tabId !== next.tabId)
  );
}

export function fallbackRestartHash(hash: string): boolean {
  return !hash || hash === "/" || hash === "/new";
}

export function rememberRestartRoute(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      RESTART_ROUTE_KEY,
      window.location.hash || "#/new",
    );
  } catch {
    // ignore storage errors
  }
}

export function maybeRestoreRestartHash(hash: string): string {
  if (typeof window === "undefined" || !fallbackRestartHash(hash)) return hash;
  try {
    const startedAt = Number(
      window.localStorage.getItem(RESTART_STARTED_KEY) ?? "0",
    );
    const storedHash = window.localStorage.getItem(RESTART_ROUTE_KEY);
    if (
      !startedAt ||
      !storedHash ||
      Date.now() - startedAt > RESTART_ROUTE_TTL_MS
    ) {
      window.localStorage.removeItem(RESTART_ROUTE_KEY);
      return hash;
    }
    window.localStorage.removeItem(RESTART_ROUTE_KEY);
    const nextHash = storedHash.startsWith("#") ? storedHash : `#${storedHash}`;
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${window.location.search}${nextHash}`,
    );
    return nextHash.slice(1);
  } catch {
    return hash;
  }
}

export function readShellRoute(): ShellRoute {
  if (typeof window === "undefined") return defaultShellRoute();
  const currentHash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  const hash = maybeRestoreRestartHash(currentHash);
  if (!hash || hash === "/" || hash === "/new") return defaultShellRoute();

  const [path, query = ""] = hash.split("?", 2);
  const params = new URLSearchParams(query);
  const rawSettingsSection = params.get("section");
  const settingsSection = isSettingsSectionKey(rawSettingsSection)
    ? rawSettingsSection
    : "overview";
  const saved: unknown = window.history.state?.cirnoReturnChat;
  const returnChat =
    saved &&
      typeof saved === "object" &&
      "hash" in saved &&
      saved.hash === window.location.hash
      ? saved
      : null;
  const activeKey =
    params.get("chat")?.trim() ||
    (returnChat && "key" in returnChat && typeof returnChat.key === "string"
      ? returnChat.key
      : null);
  const temporary = Boolean(
    returnChat && "temporary" in returnChat && returnChat.temporary === true,
  );

  const tabIdentity = returnChat && typeof window.history.state?.cirnoTabId === "string"
    ? { tabId: window.history.state.cirnoTabId as string } : {};

  if (path === "/settings") {
    return {
      view: "settings",
      activeKey,
      temporary,
      settingsSection,
      ...tabIdentity,
    };
  }
  if (path === "/apps") {
    return { view: "apps", activeKey, temporary, settingsSection: "apps", ...tabIdentity };
  }
  if (path === "/inbox")
    return { view: "inbox", activeKey, temporary, settingsSection: "overview", ...tabIdentity };
  if (path === "/automations") {
    return {
      view: "automations",
      activeKey,
      temporary,
      settingsSection: "automations",
      ...tabIdentity,
    };
  }
  if (path === "/channels") {
    return {
      view: "channels",
      activeKey,
      temporary,
      settingsSection: "channels",
      ...tabIdentity,
    };
  }

  if (path === "/skills") {
    return { view: "skills", activeKey, temporary, settingsSection: "skills", ...tabIdentity };
  }
  if (path.startsWith("/temporary/")) {
    const encoded = path.slice("/temporary/".length);
    try {
      const chatId = decodeURIComponent(encoded).trim();
      return chatId
        ? {
          view: "chat",
          activeKey: `websocket:${chatId}`,
          settingsSection: "overview",
          temporary: true,
        }
        : defaultShellRoute();
    } catch {
      return defaultShellRoute();
    }
  }
  if (path.startsWith("/chat/")) {
    const encoded = path.slice("/chat/".length);
    try {
      const key = decodeURIComponent(encoded).trim();
      return key
        ? { view: "chat", activeKey: key, settingsSection: "overview" }
        : defaultShellRoute();
    } catch {
      return defaultShellRoute();
    }
  }
  return defaultShellRoute();
}
