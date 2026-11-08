import type { ShellRoute } from "./navigation";

export function shellRouteHash(route: ShellRoute): string {
  if (route.view === "chat") {
    if (route.temporary && route.activeKey?.startsWith("websocket:")) {
      const chatId = route.activeKey.slice("websocket:".length);
      return `#/temporary/${encodeURIComponent(chatId)}`;
    }
    return route.activeKey
      ? `#/chat/${encodeURIComponent(route.activeKey)}`
      : "#/new";
  }
  const params = new URLSearchParams();
  if (route.view === "settings" && route.settingsSection !== "overview") {
    params.set("section", route.settingsSection);
  }
  const query = params.toString();
  return `#/${route.view}${query ? `?${query}` : ""}`;
}

export function writeShellRoute(route: ShellRoute, replace = false): void {
  if (typeof window === "undefined") return;
  const nextHash = shellRouteHash(route);
  const state = {
    ...window.history.state,
    cirnoTabId: route.tabId ?? null,
    cirnoReturnChat:
      route.view === "chat"
        ? null
        : {
          hash: nextHash,
          key: route.activeKey,
          temporary: route.temporary === true,
        },
  };
  const url = `${window.location.pathname}${window.location.search}${nextHash}`;
  if (replace || window.location.hash === nextHash) {
    window.history.replaceState(state, "", url);
  } else {
    window.history.pushState(state, "", url);
  }
}
