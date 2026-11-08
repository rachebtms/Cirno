import { useEffect, useState } from "react";

import {
  AutomationRunDialogView,
  type AutomationRunRecord,
} from "./AutomationRunDialogView";
import { fetchAutomationRunResult } from "@/lib/api";
import type { SessionAutomationJob } from "@/lib/contracts/automations";

export type { AutomationRunRecord } from "./AutomationRunDialogView";

export function AutomationRunDialog({
  token = "",
  job,
  run,
  locale,
  open,
  onOpenChange,
}: {
  token?: string;
  job: SessionAutomationJob;
  run: AutomationRunRecord;
  locale: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [attempt, setAttempt] = useState(0);
  const kind = job.kind === "local_trigger" ? "local_trigger" : "cron";
  const resultKey = JSON.stringify([
    token,
    kind,
    job.id,
    run.run_at_ms,
    attempt,
  ]);
  const [result, setResult] = useState<{
    key: string;
    status: "loading" | "loaded" | "error";
    response: string | null;
    error?: string;
  } | null>(null);
  useEffect(() => {
    if (!open) return;
    if (!token) {
      setResult({ key: resultKey, status: "loaded", response: null });
      return;
    }
    const controller = new AbortController();
    setResult({ key: resultKey, status: "loading", response: null });
    void fetchAutomationRunResult(
      token,
      job.id,
      run.run_at_ms,
      kind,
      controller.signal,
    )
      .then((payload) => {
        if (!controller.signal.aborted) {
          setResult({
            key: resultKey,
            status: "loaded",
            response: payload.response,
          });
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setResult({
            key: resultKey,
            status: "error",
            response: null,
            error: reason instanceof Error ? reason.message : String(reason),
          });
        }
      });
    return () => controller.abort();
  }, [job.id, kind, open, resultKey, run.run_at_ms, token]);
  const currentResult = result?.key === resultKey ? result : null;
  return (
    <AutomationRunDialogView
      job={job}
      run={run}
      locale={locale}
      open={open}
      result={currentResult ?? { status: "loading", response: null }}
      onRetry={() => setAttempt((value) => value + 1)}
      onOpenChange={onOpenChange}
    />
  );
}
