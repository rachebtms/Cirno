import { useDeferredTitleRefresh } from "@/hooks/useDeferredTitleRefresh";
import { fetchSettings } from "@/lib/api";
import { useCallback, useEffect } from "react";
import type { ComponentInputs } from "./inputs";
import {
  RESTART_ROUTE_KEY,
  RESTART_STARTED_KEY,
  defaultShellRoute,
  readShellRoute,
  rememberRestartRoute,
} from "./navigation";
import type { useConversationProjection } from "./useConversationProjection";
import type { useConversationState } from "./useConversationState";
import type { useWorkspaceState } from "./useWorkspaceState";

export function useRuntimeActions({
  workspaceState,
  conversationProjection,
  conversationState,
  inputs,
}: {
  workspaceState: ReturnType<typeof useWorkspaceState>;
  conversationProjection: ReturnType<typeof useConversationProjection>;
  conversationState: ReturnType<typeof useConversationState>;
  inputs: ComponentInputs;
}) {
  const {
          client,
    restartSawDisconnectRef,
    restartStartedAtRef,
    setIsRestarting,
    setRestartToast,
    runningChatIdsRef,
    setRunningChatIds,
    setUpdatedChatIds,
    temporarySessionsRef,
    activeChatIdRef,
    filePreviewStore,
    setTemporarySessions,
    getToken,
    settingsRefreshGenerationRef,
    setSettingsSnapshot,
    t,
    temporaryChatActive,
    refresh,
  } = workspaceState;
  const { navigate } = conversationProjection;
  const { activeSession, activePaneSession } = conversationState;
  const { onModelNameChange } = inputs;
  const onRestart = useCallback(() => {
    const chatId = activeSession?.chatId ?? client.defaultChatId;
    if (!chatId) return;
    restartSawDisconnectRef.current = false;
    restartStartedAtRef.current = Date.now();
    setIsRestarting(true);
    rememberRestartRoute();
    try {
      window.localStorage.setItem(
        RESTART_STARTED_KEY,
        String(restartStartedAtRef.current),
      );
    } catch {
      // ignore storage errors
    }
    void client
      .sendSystemCommand(chatId, "/restart")
      .catch((error: unknown) => {
        if (restartSawDisconnectRef.current) return; // A disconnect is expected during restart.
        restartStartedAtRef.current = 0;
        setIsRestarting(false);
        setRestartToast(error instanceof Error ? error.message : String(error));
        try {
          window.localStorage.removeItem(RESTART_STARTED_KEY);
          window.localStorage.removeItem(RESTART_ROUTE_KEY);
        } catch {
          /* The visible error does not depend on browser storage. */
        }
      });
  }, [activeSession?.chatId, client]);
  useEffect(() => {
    return client.onRuntimeModelUpdate((modelName) => {
      onModelNameChange(modelName);
    });
  }, [client, onModelNameChange]);
  useEffect(() => {
    return client.onRunStatus((chatId, state) => {
      if (state.active) {
        const nextRunning = new Set(runningChatIdsRef.current);
        nextRunning.add(chatId);
        runningChatIdsRef.current = nextRunning;
        setRunningChatIds(nextRunning);
        setUpdatedChatIds((current) => {
          if (!current.has(chatId)) return current;
          const next = new Set(current);
          next.delete(chatId);
          return next;
        });
        return;
      }

      if (!runningChatIdsRef.current.has(chatId)) return;
      const nextRunning = new Set(runningChatIdsRef.current);
      nextRunning.delete(chatId);
      runningChatIdsRef.current = nextRunning;
      setRunningChatIds(nextRunning);
      if (
        Object.values(temporarySessionsRef.current).some(
          (session) => session.chatId === chatId,
        )
      )
        return;
      setUpdatedChatIds((current) => {
        const next = new Set(current);
        if (activeChatIdRef.current === chatId) {
          next.delete(chatId);
        } else {
          next.add(chatId);
        }
        return next;
      });
    });
  }, [client]);
  useEffect(() => {
    let wasOpen = client.status === "open";
    return client.onStatus((status) => {
      if (status === "open") {
        wasOpen = true;
        return;
      }
      if (!wasOpen) return;
      wasOpen = false;
      filePreviewStore.clear();
      if (Object.keys(temporarySessionsRef.current).length === 0) return;
      temporarySessionsRef.current = {};
      setTemporarySessions({});
      if (readShellRoute().temporary) {
        navigate(defaultShellRoute(), { replace: true });
      }
    });
  }, [client, navigate, filePreviewStore]);
  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;
    const refreshSettings = (generation: number, attempt = 0): void => {
      void fetchSettings(getToken())
        .then((payload) => {
          if (
            !cancelled &&
            generation === settingsRefreshGenerationRef.current
          ) {
            setSettingsSnapshot(payload);
          }
        })
        .catch(() => {
          if (
            cancelled ||
            generation !== settingsRefreshGenerationRef.current ||
            attempt >= 3
          )
            return;
          retryTimer = window.setTimeout(
            () => refreshSettings(generation, attempt + 1),
            250,
          );
        });
    };
    const unsubscribe = client.onStatus((status) => {
      // Another tab can consume the reload marker before this tab reconnects.
      const startedAt =
        restartStartedAtRef.current ||
        (() => {
          try {
            return Number(
              window.localStorage.getItem(RESTART_STARTED_KEY) ?? "0",
            );
          } catch {
            return 0;
          }
        })();
      if (!startedAt) return;
      if (status !== "open") {
        restartStartedAtRef.current = startedAt;
        restartSawDisconnectRef.current = true;
        return;
      }
      const elapsedMs = Date.now() - startedAt;
      if (!restartSawDisconnectRef.current && elapsedMs < 1500) return;
      try {
        window.localStorage.removeItem(RESTART_STARTED_KEY);
        window.localStorage.removeItem(RESTART_ROUTE_KEY);
      } catch {
        // ignore storage errors
      }
      const refreshGeneration = ++settingsRefreshGenerationRef.current;
      restartStartedAtRef.current = 0;
      setIsRestarting(false);
      setRestartToast(
        t("app.restart.completed", { seconds: (elapsedMs / 1000).toFixed(1) }),
      );
      window.setTimeout(() => setRestartToast(null), 3_500);
      refreshSettings(refreshGeneration);
    });
    return () => {
      cancelled = true;
      unsubscribe();
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, [client, getToken, t]);
  const onTurnEnd = useDeferredTitleRefresh(
    temporaryChatActive ? null : activePaneSession,
    refresh,
  );
  return { onTurnEnd, onRestart };
}
