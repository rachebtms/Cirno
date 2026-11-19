import type { Dispatch, SetStateAction } from "react";
import type { TFunction } from "i18next";
import type { PendingRestartSections } from "@/features/settings/contracts";
import type { SystemSettingsState } from "./useSystemSettingsState";
import type { CirnoClient } from "@/lib/cirno-client";
import type { McpOAuthFlowPayload } from "@/lib/contracts/mcp";
import { cancelMcpOAuth, completeMcpOAuth, fetchMcpOAuthStatus, fetchMcpPresets, startMcpOAuth } from "@/lib/api";
import { notifyMcpPresetsChanged } from "@/lib/mcp-preset-events";

interface Options {
  state: SystemSettingsState;
  client: CirnoClient;
  getToken: () => string;
  t: TFunction;
  setPendingRestartSections: Dispatch<SetStateAction<PendingRestartSections>>;
  beginAction: (key: string) => boolean;
  endAction: (key: string) => void;
  retireProxyDrafts: (names: string[]) => void;
}

/** One settings surface owns its browser flow, status reads and pending callback. */
export function createMcpOAuthActions({ state, client, getToken, t, setPendingRestartSections,
  beginAction, endAction, retireProxyDrafts }: Options) {
  const { isSystemSettingsCurrent: isCurrent, mcpActionRef, mcpOAuthFlowRef: flowRef,
    mcpOAuthPopupRef: popupRef, mcpOAuthNavigatedUrlRef: navigatedRef,
    mcpOAuthRevisionRef: revisionRef, mcpOAuthCompletingRef: completingRef,
    mcpOAuthMonitorRef: monitorRef,
    mcpOAuthCancellingRef: cancellingRef, mcpOAuthWaitRef: waitRef,
    setMcpOAuthFlow, setMcpOAuthCallbackUrl, setMcpOAuthCompleting, setMcpOAuthCallbackError,
    setMcpOAuthPopupBlocked, setMcpPresets, setMcpMessage, setMcpError } = state;
  const keyFor = (flow: McpOAuthFlowPayload) => `oauth:${flow.name}`;
  const ownsFlow = (flow: McpOAuthFlowPayload) => isCurrent()
    && flowRef.current?.flow_id === flow.flow_id && mcpActionRef.current === keyFor(flow);

  const closePopup = () => {
    const popup = popupRef.current;
    popupRef.current = null;
    navigatedRef.current = null;
    try { if (popup && !popup.closed) popup.close(); } catch { /* Cross-origin WindowProxy. */ }
  };
  const openPopup = (url?: string) => {
    let popup: Window | null = null;
    try {
      popup = window.open(url ?? "about:blank", "cirno-mcp-oauth", "popup,width=560,height=720,resizable=yes,scrollbars=yes");
      if (popup) {
        popupRef.current = popup;
        navigatedRef.current = url ?? null;
        if (!url) {
          try {
            popup.document.title = t("settings.oauth.signingIn", { defaultValue: "Preparing sign-in…" });
            popup.document.body.textContent = t("settings.mcp.preparingSignIn");
          } catch { /* The window may have been reused and already navigated. */ }
        }
        try { popup.opener = null; popup.focus(); } catch { /* Cross-origin WindowProxy. */ }
      }
    } catch { /* The browser may block popup creation. */ }
    setMcpOAuthPopupBlocked(!popup);
  };
  const navigatePopup = (flow: McpOAuthFlowPayload) => {
    const url = flow.authorization_url;
    if (!url) return;
    const popup = popupRef.current;
    // COOP isolation can make an already navigated authorization tab appear closed.
    if (popup && navigatedRef.current === url) return;
    try {
      if (popup && !popup.closed) {
        popup.location.replace(url); navigatedRef.current = url;
        popup.focus(); setMcpOAuthPopupBlocked(false); return;
      }
      if (popup) return;
    } catch { /* Expose the explicit Continue in browser action. */ }
    setMcpOAuthPopupBlocked(true);
  };
  const clearFlow = () => {
    revisionRef.current += 1;
    monitorRef.current += 1;
    waitRef.current?.();
    closePopup();
    flowRef.current = null;
    completingRef.current = false;
    setMcpOAuthFlow(null);
    setMcpOAuthCallbackUrl("");
    setMcpOAuthCompleting(false);
    setMcpOAuthCallbackError(null);
  };
  const waitToPoll = () => new Promise<void>(resolve => {
    const release = () => {
      window.clearTimeout(timer);
      if (waitRef.current === release) waitRef.current = null;
      resolve();
    };
    const timer = window.setTimeout(release, 800);
    waitRef.current = release;
  });
  const finish = async (flow: McpOAuthFlowPayload) => {
    if (!ownsFlow(flow)) return;
    clearFlow();
    const key = keyFor(flow);
    try {
      if (flow.status === "connected") {
        const payload = await fetchMcpPresets(getToken());
        if (!isCurrent() || mcpActionRef.current !== key) return;
        setMcpPresets(payload);
        if (payload.presets.some(preset => preset.runtime_status === "connecting")) state.mcpRefreshRef.current?.();
        retireProxyDrafts([flow.name]);
        notifyMcpPresetsChanged(payload);
        setMcpMessage(null); setMcpError(null);
      } else if (flow.status === "authorized" && flow.hot_reload) {
        if (flow.hot_reload.requires_restart) setPendingRestartSections(prev => ({ ...prev, runtime: true }));
        setMcpError(flow.hot_reload.message || t("settings.mcp.reloadFailed"));
      } else if (flow.status === "failed") {
        setMcpError(flow.error || t("settings.mcp.oauthFailed"));
      }
    } catch (err) {
      if (isCurrent() && mcpActionRef.current === key) setMcpError((err as Error).message);
    } finally { endAction(key); }
  };
  const monitor = async (initial: McpOAuthFlowPayload) => {
    const generation = ++monitorRef.current;
    const ownsMonitor = () => ownsFlow(initial) && generation === monitorRef.current && !cancellingRef.current;
    while (ownsMonitor()) {
      const current = flowRef.current!;
      navigatePopup(current);
      if (["connected", "failed", "cancelled"].includes(current.status)
        || current.status === "authorized" && current.hot_reload) {
        await finish(current); return;
      }
      await waitToPoll();
      if (!ownsMonitor()) return;
      if (completingRef.current) continue;
      const revision = revisionRef.current;
      try {
        const next = await fetchMcpOAuthStatus(getToken(), initial.flow_id);
        if (!ownsMonitor()) return;
        if (revision !== revisionRef.current) continue;
        flowRef.current = next;
        setMcpOAuthFlow(next);
      } catch (err) {
        if (!ownsMonitor()) return;
        if (revision !== revisionRef.current) continue;
        clearFlow(); endAction(keyFor(initial));
        setMcpError((err as Error).message); return;
      }
    }
  };
  const handleMcpOAuthConnect = async (name: string, reset = false, values: Record<string, string> = {}) => {
    const key = `oauth:${name}`;
    if (!beginAction(key)) return;
    revisionRef.current += 1;
    cancellingRef.current = false;
    completingRef.current = false;
    openPopup(); setMcpMessage(null); setMcpError(null);
    setMcpOAuthCallbackUrl(""); setMcpOAuthCompleting(false); setMcpOAuthCallbackError(null);
    try {
      const flow = await startMcpOAuth(client, name, reset, values);
      if (!isCurrent() || mcpActionRef.current !== key) return;
      flowRef.current = flow;
      setMcpOAuthFlow(flow);
      void monitor(flow);
    } catch (err) {
      if (!isCurrent() || mcpActionRef.current !== key) return;
      clearFlow(); endAction(key);
      setMcpError((err as Error).message);
    }
  };
  const handleMcpOAuthCancel = async () => {
    const flow = flowRef.current;
    if (!flow || !ownsFlow(flow) || cancellingRef.current) return;
    cancellingRef.current = true;
    revisionRef.current += 1;
    monitorRef.current += 1;
    waitRef.current?.(); closePopup();
    try {
      await cancelMcpOAuth(client, flow.flow_id);
      if (!ownsFlow(flow)) return;
      clearFlow(); endAction(keyFor(flow));
      setMcpError(null);
    } catch (err) {
      if (!ownsFlow(flow)) return;
      cancellingRef.current = false;
      setMcpError((err as Error).message);
      void monitor(flow);
    } finally {
      if (isCurrent()) cancellingRef.current = false;
    }
  };
  const handleMcpOAuthOpen = () => {
    const flow = flowRef.current;
    if (flow && ownsFlow(flow) && !cancellingRef.current && flow.authorization_url) openPopup(flow.authorization_url);
  };
  const handleMcpOAuthComplete = async () => {
    const flow = flowRef.current;
    if (!flow || !ownsFlow(flow) || completingRef.current || cancellingRef.current || flow.completion_input !== "callback_url") return;
    const callbackUrl = state.mcpOAuthCallbackUrl.trim();
    if (!callbackUrl) { setMcpOAuthCallbackError(t("settings.oauth.pasteCallbackToContinue")); return; }
    completingRef.current = true;
    const revision = ++revisionRef.current;
    setMcpOAuthCompleting(true); setMcpOAuthCallbackError(null);
    const ownsCompletion = () => ownsFlow(flow) && revision === revisionRef.current;
    try {
      const next = await completeMcpOAuth(client, flow.flow_id, callbackUrl);
      if (!ownsCompletion()) return;
      flowRef.current = next; setMcpOAuthFlow(next);
    } catch (err) {
      if (ownsCompletion()) setMcpOAuthCallbackError((err as Error).message);
    } finally {
      if (ownsFlow(flow)) {
        revisionRef.current += 1;
        completingRef.current = false;
        setMcpOAuthCompleting(false);
      }
    }
  };
  return { handleMcpOAuthConnect, handleMcpOAuthCancel, handleMcpOAuthOpen, handleMcpOAuthComplete };
}
