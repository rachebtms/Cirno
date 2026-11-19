import { useCallback, useEffect, useMemo, useState } from "react";

import { useClient } from "@/providers/ClientProvider";
import { useLifetime } from "@/ui/resources/useLifetime";
import { useCirnoStream } from "@/hooks/useCirnoStream";
import {
  deleteSession as apiDeleteSession,
  fetchSessionAutomations,
  listSessions,
} from "@/lib/api";
import { webuiThreadCache } from "@/lib/webui-thread-cache";
import { readReloadSessions, writeReloadCache } from "@/lib/reload-cache";
import type { ChatSummary, SessionDeleteResult } from "@/lib/contracts/conversations";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";

const CHAT_CREATE_TIMEOUT_MS = 60_000;

/** Sidebar state: fetches the full session list and exposes create / delete actions. */
export function useSessions(): {
  sessions: ChatSummary[];
  loading: boolean;
  initialLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  createChat: (
    workspaceScope?: WorkspaceScopePayload | null,
    modelPreset?: string | null,
    projectId?: string | null,
    ptcMode?: boolean,
  ) => Promise<string>;
  forkChat: (sourceChatId: string, beforeUserIndex: number, title?: string) => Promise<string>;
  deleteChat: (
    key: string,
    options?: { deleteAutomations?: boolean },
  ) => Promise<SessionDeleteResult>;
  getSessionAutomations: (key: string) => Promise<SessionAutomationJob[]>;
} {
  const { client, token } = useClient();
  const owner = useMemo(() => ({ client, token: "", revision: 0, optimisticKeys: new Set<string>(), refreshPending: false, refreshInFlight: null as Promise<void> | null }), [client]);
  owner.token = token;
  const current = useLifetime(owner);
  const requireCurrent = useCallback(() => { if (!current()) throw new Error("Conversation connection changed"); }, [current]);
  const [sessions, setSessions] = useState<ChatSummary[]>(readReloadSessions);
  const [loadedOnce, setLoadedOnce] = useState(() => sessions.length > 0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stateOwner, setStateOwner] = useState(owner);
  if (stateOwner !== owner) {
    setStateOwner(owner); setSessions([]); setLoadedOnce(false); setLoading(true); setError(null);
  }

  useEffect(() => {
    if (current() && (sessions.length || !loading)) writeReloadCache("sessions", sessions.slice(0, 200));
  }, [sessions, loading, current]);

  const refresh = useCallback((): Promise<void> => {
    if (!current()) return Promise.resolve();
    owner.refreshPending = true;
    if (owner.refreshInFlight) return owner.refreshInFlight;
    const request = (async () => {
      setLoading(true);
      try {
        while (current() && owner.refreshPending) {
          owner.refreshPending = false;
          try {
            const revision = owner.revision;
            const rows = await listSessions(owner.token);
            if (!current()) return;
            if (revision !== owner.revision) { owner.refreshPending = true; continue; }
            setLoadedOnce(true);
            const serverKeys = new Set(rows.map((row) => row.key));
            setSessions((prev) => {
              if (!current()) return prev;
              const byKey = new Map(prev.map((row) => [row.key, row]));
              const next = [
                ...rows.map((row) => {
                  const previous = byKey.get(row.key);
                  return previous && JSON.stringify(previous) === JSON.stringify(row) ? previous : row;
                }),
                ...prev.filter(
                  (session) =>
                    owner.optimisticKeys.has(session.key)
                    && !serverKeys.has(session.key),
                ),
              ];
              return next.length === prev.length && next.every((row, index) => row === prev[index]) ? prev : next;
            });
            for (const key of Array.from(owner.optimisticKeys)) {
              if (serverKeys.has(key)) owner.optimisticKeys.delete(key);
            }
            setError(null);
          } catch (e) {
            if (current()) setError(e instanceof Error ? e.message : String(e));
          }
        }
      } finally {
        owner.refreshInFlight = null;
        if (current()) setLoading(false);
      }
    })();
    owner.refreshInFlight = request;
    return request;
  }, [owner, current]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const unsubscribe = client.onSessionUpdate(() => {
      if (timer !== undefined) return;
      timer = setTimeout(() => {
        timer = undefined;
        void refresh();
      }, 250);
    });
    return () => {
      clearTimeout(timer);
      unsubscribe();
    };
  }, [client, refresh]);

  const createChat = useCallback(async (
    workspaceScope?: WorkspaceScopePayload | null,
    modelPreset?: string | null,
    projectId?: string | null,
    ptcMode = false,
  ): Promise<string> => {
    requireCurrent();
    const chatId = await client.newChat(CHAT_CREATE_TIMEOUT_MS, workspaceScope, projectId, ptcMode);
    requireCurrent();
    const key = `websocket:${chatId}`;
    owner.optimisticKeys.add(key);
    owner.revision++;
    // Optimistic insert; a subsequent refresh will replace it with the
    // authoritative row once the server persists the session.
    setSessions((prev) => !current() ? prev : [
      {
        key,
        channel: "websocket",
        chatId,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        title: "",
        preview: "",
        modelPreset: modelPreset ?? null,
        projectId: projectId ?? null,
        ptcMode,
        workspaceScope: workspaceScope ?? null,
        projectLocked: false,
      },
      ...prev.filter((s) => s.key !== key),
    ]);
    return chatId;
  }, [client, owner, current, requireCurrent]);

  const forkChat = useCallback(async (
    sourceChatId: string,
    beforeUserIndex: number,
    title?: string,
  ): Promise<string> => {
    requireCurrent();
    const chatId = await client.forkChat(
      sourceChatId,
      beforeUserIndex,
      title,
      CHAT_CREATE_TIMEOUT_MS,
    );
    requireCurrent();
    const key = `websocket:${chatId}`;
    owner.optimisticKeys.add(key);
    owner.revision++;
    setSessions((prev) => !current() ? prev : [
      {
        key,
        channel: "websocket",
        chatId,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        title: title ?? "",
        preview: "",
        workspaceScope: null,
      },
      ...prev.filter((s) => s.key !== key),
    ]);
    return chatId;
  }, [client, owner, current, requireCurrent]);

  const deleteChat = useCallback(
    async (key: string, options?: { deleteAutomations?: boolean }) => {
      requireCurrent();
      const optimistic = owner.optimisticKeys.has(key);
      const result = await apiDeleteSession(client, key, options);
      requireCurrent();
      if (result.blocked_by_automations || (!result.deleted && !optimistic)) return result;
      owner.optimisticKeys.delete(key);
      owner.revision++;
      webuiThreadCache.delete(key);
      setSessions((prev) => current() ? prev.filter((s) => s.key !== key) : prev);
      // The gateway may have restarted and forgotten an unpersisted chat's
      // draft scope, but removing that optimistic session is still a deletion.
      return result.deleted ? result : { ...result, deleted: true };
    },
    [client, owner, current, requireCurrent],
  );

  const getSessionAutomations = useCallback(async (key: string) => {
    requireCurrent();
    const result = await fetchSessionAutomations(owner.token, key);
    requireCurrent();
    return result.jobs;
  }, [owner, requireCurrent]);

  return {
    sessions,
    loading,
    initialLoading: loading && !loadedOnce,
    error,
    refresh,
    createChat,
    forkChat,
    deleteChat,
    getSessionAutomations,
  };
}

/** Read-only history view backed by the conversation owner. */
export function useSessionHistory(key: string | null) {
  const { messages, history, refreshHistory, loadOlder } = useCirnoStream(
    null, undefined, false, undefined, undefined, undefined, { key },
  );
  return { messages, ...history, refresh: refreshHistory, loadOlder };
}
