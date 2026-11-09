import { useCallback, useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { HoverHint } from "@/components/ui/tooltip";
import { headerControlClassName } from "./header-control";
import { ROUTER_CHAT_ID } from "@/lib/conversation-role";
import type { CirnoClient } from "@/lib/cirno-client";

type HeartbeatState = { paused: boolean; enabled: boolean };

export function RouterHeartbeatButton({ client }: { client: CirnoClient }) {
  const { t } = useTranslation();
  const [state, setState] = useState<HeartbeatState | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const epoch = useRef(0), mutating = useRef(false);
  const refresh = useCallback(async () => {
    const ticket = ++epoch.current;
    try {
      const result = await client.requestMutation<HeartbeatState>("instance.action", { action: "router.heartbeat", values: {} });
      if (ticket === epoch.current) { setState(result); setError(""); }
    } catch (reason) { if (ticket === epoch.current) setError(String(reason instanceof Error ? reason.message : reason)); }
  }, [client]);
  useEffect(() => {
    void refresh();
    const removeUpdate = client.onSessionUpdate(chatId => { if (chatId === ROUTER_CHAT_ID && !mutating.current) void refresh(); });
    const removeStatus = client.onStatus(status => { if (status === "open" && !mutating.current) void refresh(); });
    return () => { epoch.current++; removeUpdate(); removeStatus(); };
  }, [client, refresh]);
  async function toggle() {
    if (mutating.current) return;
    if (!state) { void refresh(); return; }
    mutating.current = true; setBusy(true); setError("");
    const ticket = ++epoch.current;
    try {
      const result = await client.requestMutation<HeartbeatState>("instance.action", { action: "router.heartbeat.update", values: { paused: !state.paused } });
      if (ticket === epoch.current) setState(result);
    } catch (reason) { if (ticket === epoch.current) setError(String(reason instanceof Error ? reason.message : reason)); }
    finally { mutating.current = false; setBusy(false); }
  }
  const label = t(state?.paused ? "thread.heartbeat.resume" : "thread.heartbeat.pause");
  return <>
    <HoverHint content={error || (state?.enabled === false ? t("thread.heartbeat.disabled") : label)}>
      <Button type="button" variant="ghost" size="icon" className={headerControlClassName}
        aria-label={label} aria-pressed={state?.paused ?? false} disabled={busy || state?.enabled === false}
        onClick={() => void toggle()}>
        {state?.paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
      </Button>
    </HoverHint>
    {error && <span role="alert" className="max-w-48 truncate text-xs text-destructive" title={error}>{error}</span>}
  </>;
}
