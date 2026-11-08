import { useEffect, useState } from "react";
import { usePageVisibility } from "@/hooks/usePageVisibility";
import { fetchSessionAutomations } from "@/lib/api";
import type { SessionAutomationJob } from "@/lib/contracts/automations";

const AUTOMATIONS_REFRESH_MS = 3000;
interface Snapshot {
  token: string;
  sessionKey: string;
  jobs: SessionAutomationJob[] | null;
  error: string | null;
}
export function useSessionAutomationJobs(
  open: boolean,
  token: string,
  sessionKey: string,
) {
  const pageVisible = usePageVisibility();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!open || !pageVisible) return;
    const controller = new AbortController();
    let refreshing = false;
    setSnapshot((current) =>
      current?.token === token && current.sessionKey === sessionKey
        ? { ...current, error: null }
        : { token, sessionKey, jobs: null, error: null },
    );
    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        const next = await fetchSessionAutomations(
          token,
          sessionKey,
          "",
          controller.signal,
        );
        if (!controller.signal.aborted)
          setSnapshot({ token, sessionKey, jobs: next.jobs, error: null });
      } catch (reason) {
        if (!controller.signal.aborted)
          setSnapshot((current) => ({
            token,
            sessionKey,
            jobs: current?.jobs ?? null,
            error: reason instanceof Error ? reason.message : String(reason),
          }));
      } finally {
        refreshing = false;
      }
    };
    void refresh();
    const interval = window.setInterval(
      () => void refresh(),
      AUTOMATIONS_REFRESH_MS,
    );
    window.addEventListener("focus", refresh);
    return () => {
      controller.abort();
      window.clearInterval(interval);
      window.removeEventListener("focus", refresh);
    };
  }, [open, pageVisible, token, sessionKey]);
  useEffect(() => {
    if (!open || !pageVisible) return;
    setNow(Date.now());
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [open, pageVisible]);
  const current =
    snapshot?.token === token && snapshot.sessionKey === sessionKey
      ? snapshot
      : null;
  return {
    jobs: current?.jobs ?? [],
    loading: open && current?.jobs == null && !current?.error,
    loadError: current?.error ?? null,
    now,
  };
}
