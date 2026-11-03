import { useEffect } from "react";

import { persistedCanonicalRunState } from "@/lib/canonical-run-snapshot";
import { fetchLatestWebuiThread } from "@/lib/latest-thread-request";
import type { CirnoClient } from "@/lib/cirno-client";
import { webuiThreadCache } from "@/lib/webui-thread-cache";

const RECONNECT_READ_CONCURRENCY = 4;

/** Reconcile durable runs even when their threads are not mounted. */
export function useReconnectRuns(client: CirnoClient, getToken: () => string): void {
  useEffect(() => {
    let controller: AbortController | null = null;
    let disposed = false;
    const recoverRuns = (status: string) => {
      controller?.abort();
      controller = null;
      if (status !== "open") return;
      const chats = client.getUnsettledRunChatIds();
      if (chats.length === 0) return;
      controller = new AbortController();
      const signal = controller.signal;
      const jobs = chats.map((chatId) => ({
        chatId,
        generation: client.getRunGeneration(chatId),
        turnId: client.getRunTurnId(chatId),
      }));
      const recover = async ({ chatId, generation, turnId }: typeof jobs[number]) => {
        const key = `websocket:${chatId}`;
        const body = await fetchLatestWebuiThread(client, getToken(), key, signal);
        if (!body || signal.aborted) return;
        const { completedTurnIds, snapshot } = persistedCanonicalRunState(body);
        const explicitlyCompleted = turnId !== null && completedTurnIds.includes(turnId);
        if (!explicitlyCompleted && (snapshot.hasPendingToolCalls || snapshot.activeTurnId)) {
          // Refresh active traces only for the run that this read actually belongs to.
          if (turnId && snapshot.activeTurnId === turnId && client.getRunGeneration(chatId) === generation
            && client.getRunTurnId(chatId) === turnId) webuiThreadCache.set(key, body);
          return;
        }
        if (turnId && !explicitlyCompleted && !snapshot.observedTurnIds.includes(turnId)) return;
        if (!client.canReconcileCanonicalCompletion(chatId, generation, completedTurnIds, snapshot)) return;
        // Preserve the result before completion fences prune queued fragments.
        // Returning to an inactive chat can hydrate from this canonical page.
        webuiThreadCache.set(key, body);
        client.reconcileCanonicalCompletion(chatId, generation, completedTurnIds, snapshot);
      };
      let nextJob = 0;
      const worker = async () => {
        while (!signal.aborted) {
          const job = jobs[nextJob++];
          if (!job) return;
          try {
            await recover(job);
          } catch (error) {
            if (!signal.aborted) console.warn("Could not restore conversation", job.chatId, error);
          }
        }
      };
      void Promise.allSettled(Array.from({ length: Math.min(RECONNECT_READ_CONCURRENCY, jobs.length) }, worker));
    };
    const unsubscribe = client.onStatus(recoverRuns);
    let waking = false;
    const wake = async () => {
      if (waking || document.visibilityState === "hidden") return;
      waking = true;
      try {
        await client.resumeFromBackground();
        if (!disposed && client.status === "open") recoverRuns("open");
      } finally { waking = false; }
    };
    const onWake = () => { void wake().catch(error => console.warn("Could not restore connection", error)); };
    document.addEventListener("visibilitychange", onWake);
    window.addEventListener("pageshow", onWake);
    window.addEventListener("online", onWake);
    return () => {
      disposed = true;
      controller?.abort();
      unsubscribe();
      document.removeEventListener("visibilitychange", onWake);
      window.removeEventListener("pageshow", onWake);
      window.removeEventListener("online", onWake);
    };
  }, [client, getToken]);
}
