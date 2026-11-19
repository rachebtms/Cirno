import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { usePageVisibility } from "@/hooks/usePageVisibility";
import { fetchSessionAutomations } from "@/lib/api";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import { useLifetime } from "@/ui/resources/useLifetime";

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
  const { t } = useTranslation();
  const owner = useMemo(() => ({ revision: 0, pending: false }), [token, sessionKey]);
  const isCurrent = useLifetime(owner);
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
      if (refreshing || owner.pending) return;
      refreshing = true;
      const revision = ++owner.revision;
      const ownsRead = () => !controller.signal.aborted && isCurrent()
        && !owner.pending && owner.revision === revision;
      try {
        const next = await fetchSessionAutomations(
          token,
          sessionKey,
          "",
          controller.signal,
        );
        if (ownsRead())
          setSnapshot({ token, sessionKey, jobs: next.jobs, error: null });
      } catch (reason) {
        if (ownsRead())
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
  }, [open, pageVisible, token, sessionKey, owner, isCurrent]);
  const mutate = useCallback(async (
    operation: () => Promise<SessionAutomationJob[]>,
  ): Promise<SessionAutomationJob[]> => {
    if (!isCurrent()) throw new DOMException("Automation view is no longer active", "AbortError");
    if (owner.pending) throw new Error(t("settings.automations.chat.schedulerBusy"));
    owner.pending = true;
    owner.revision += 1;
    try {
      const jobs = (await operation()).filter(
        (job) => !job.protected && (
          job.webui_session_key !== undefined ? job.webui_session_key : job.origin?.session_key
        ) === sessionKey,
      );
      if (isCurrent()) setSnapshot({ token, sessionKey, jobs, error: null });
      return jobs;
    } finally {
      owner.revision += 1;
      owner.pending = false;
    }
  }, [isCurrent, owner, token, sessionKey, t]);
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
    mutate,
  };
}
