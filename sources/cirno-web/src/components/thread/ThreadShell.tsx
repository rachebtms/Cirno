import { RouterHeartbeatButton } from "./RouterHeartbeatButton";
import { headerControlClassName } from "@/components/thread/header-control";
import { conversationRole } from "@/lib/conversation-role";
import { QuestionReplyProvider, UserQuestionQueue } from "@/components/thread/UserQuestionCard";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { HoverHint } from "@/components/ui/tooltip";
import { useWorkspaceOpen } from "@/features/workbench/context";
import type { UserQuestion } from "@/lib/contracts/messages";
import { hasToolHistory } from "@/lib/thread-inputs";
import { formatQuestionAnswer } from "@/lib/user-question";
import { scopeWithAccessMode } from "@/lib/workspace";
import { FolderOpen, Route } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { hasInlineDeliveryError, latestActiveTurnId } from "./composer-usage";
import { HeroGreeting, randomHeroGreetingKey } from "./HeroGreeting";
import { resolveModelPresetSelection } from "./model-preset";
import { ThreadPreview } from "./ThreadPreview";
import { useInstalledSettingItems } from "./useInstalledSettingItems";
import { useMessageEditing } from "@/features/messages/model/useMessageEditing";
import { useThreadModels } from "./useThreadModels";
import { useThreadPreview } from "./useThreadPreview";
import { useThreadUsage } from "./useThreadUsage";

import { FileActionsProvider } from "@/components/FileActions";
import { FilePreviewAvailabilityProvider } from "@/components/FilePreviewAvailabilityContext";
import { SessionHandleLabel } from "@/components/SessionHandleLabel";
import { ClearConversationButton } from "@/components/thread/ClearConversationButton";
import { ModelFallbackNotice } from "@/components/thread/ModelFallbackNotice";
import { PromptNavigator } from "@/components/thread/PromptNavigator";
import { SessionAutomations } from "@/features/automations/session/SessionAutomations";
import { StreamErrorNotice } from "@/components/thread/StreamErrorNotice";
import { SubagentTaskDock } from "@/components/thread/SubagentTaskDock";
import { SubagentTasksProvider } from "@/components/thread/SubagentTasks";
import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { ThreadLoadingSkeleton } from "@/components/thread/ThreadLoadingSkeleton";
import { ThreadViewport } from "@/components/thread/ThreadViewport";
import type { ThreadViewportHandle } from "@/components/thread/viewport/contracts";
import { useCirnoStream, type SendAttachment, type SendOptions } from "@/hooks/useCirnoStream";
import { type FilePreviewStore } from "@/hooks/useFilePreviewState";
import { usePromptHistory } from "@/hooks/usePromptHistory";
import {
  fetchInstalledCliApps,
  fetchMcpPresets,
  fetchWorkspaceDirectories,
  fetchWorkspaces,
  listSlashCommands
} from "@/lib/api";
import {
  CLI_APPS_CHANGED_EVENT,
  installedCliAppsFromPayload,
  isCliAppsPayload,
} from "@/lib/cli-app-events";
import type { ComposerDraft, ComposerDraftStore } from "@/lib/composer-draft";
import type { SlashCommand } from "@/lib/contracts/commands";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { SkillSummary } from "@/lib/contracts/skills";
import type { ProjectDirectory, WorkspaceScopePayload, WorkspacesPayload } from "@/lib/contracts/workspaces";
import {
  MCP_PRESETS_CHANGED_EVENT,
  installedMcpPresetsFromPayload,
  isMcpPresetsPayload,
} from "@/lib/mcp-preset-events";
import { resolveModelRequestFailureCopy } from "@/lib/model-request-failure";
import { providerDisplayLabel } from "@/lib/provider-brand";
import { latestSubagentInputKey } from "@/lib/subagent-tasks";
import { projectWebuiThreadMessages } from "@/lib/thread-display-projection";
import { projectThreadEvents } from "@/lib/thread-event-projection";
import { ThreadMessageCache } from "@/lib/thread-message-cache";
import { cn } from "@/lib/utils";
import { useClient } from "@/providers/ClientProvider";
import { isLocalAttachment } from "../../../packages/client-events/attachments";

const EMPTY_TITLE_OVERRIDES: Record<string, string> = {};

interface ThreadShellProps {
  session: ChatSummary | null;
  sessions?: ChatSummary[];
  titleOverrides?: Record<string, string>;
  title: string;
  temporary?: boolean;
  temporaryChatIds?: readonly string[];
  messageCache?: ThreadMessageCache;
  filePreviewStore?: FilePreviewStore;
  draftStore?: ComposerDraftStore;
  ptcModeEnabled?: boolean;
  onPtcModeEnabledChange?: (enabled: boolean) => void;
  temporaryChatEnabled?: boolean;
  onTemporaryChatEnabledChange?: (enabled: boolean) => void;
  onToggleSidebar: () => void;
  onCreateChat?: (
    workspaceScope?: WorkspaceScopePayload | null,
    initialMessage?: string,
    modelPreset?: string | null,
  ) => Promise<string | null>;
  pendingFirstMessage?: PendingFirstMessage & { id: string; chatId: string } | null;
  onPendingFirstMessageConsumed?: (id: string) => void;
  onForkChat?: (sourceChatId: string, beforeUserIndex: number) => Promise<string | null>;
  onTurnEnd?: () => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
  hideDesktopSidebarToggle?: boolean;
  hideSidebarToggle?: boolean;
  hideThemeButton?: boolean;
  hideHeaderTitle?: boolean;
  inlineHandle?: boolean;
  hideHeader?: boolean;
  headerActions?: ReactNode;
  headerPortalTarget?: HTMLElement | null;
  headerActive?: boolean;
  composerPortalTarget?: HTMLElement | null;
  navigationFrame?: HTMLElement | null;
  composerActive?: boolean;
  composerInputAriaLabel?: string;
  emptyComposerVariant?: "hero" | "thread";
  workspaceScope?: WorkspaceScopePayload | null;
  workspaceDefaultScope?: WorkspaceScopePayload | null;
  workspaceControls?: WorkspacesPayload["controls"] | null;
  workspaceScopeDisabled?: boolean;
  workspaceError?: string | null;
  onWorkspaceScopeChange?: (scope: WorkspaceScopePayload) => void;
  settingsSnapshot?: SettingsPayload | null;
  settingsLoading?: boolean;
  onOpenModelSettings?: () => void;
  skills?: SkillSummary[];
}

interface PendingFirstMessage {
  finish?: (accepted: boolean) => void;
  content: string;
  images?: SendAttachment[];
  options?: SendOptions;
}

export function ThreadShell({
  session,
  sessions = [],
  titleOverrides = EMPTY_TITLE_OVERRIDES,
  title,
  temporary = false,
  temporaryChatIds = [],
  messageCache,
  filePreviewStore,
  draftStore,
  ptcModeEnabled = false,
  onPtcModeEnabledChange,
  temporaryChatEnabled = false,
  onTemporaryChatEnabledChange,
  onToggleSidebar,
  onCreateChat,
  pendingFirstMessage = null,
  onPendingFirstMessageConsumed,
  onForkChat,
  onTurnEnd,
  theme = "light",
  onToggleTheme = () => { },
  hideDesktopSidebarToggle = false,
  hideSidebarToggle = false,
  hideThemeButton = false,
  hideHeaderTitle = false,
  inlineHandle = false,
  hideHeader = false,
  headerActions,
  headerPortalTarget,
  headerActive = true,
  composerPortalTarget,
  navigationFrame,
  composerActive = true,
  composerInputAriaLabel,
  emptyComposerVariant = "hero",
  workspaceScope = null,
  workspaceDefaultScope = null,
  workspaceControls = null,
  workspaceScopeDisabled = false,
  workspaceError = null,
  onWorkspaceScopeChange,
  settingsSnapshot = null,
  settingsLoading = false,
  onOpenModelSettings,
  skills = [],
}: ThreadShellProps) {
  const { t } = useTranslation();
  const chatId = session?.chatId ?? null;
  const {
    settings, modelSettingsError, modelFallback, setModelFallback, modelPresetError, localModelPreset,
    activeModelPreset, handleModelPresetChange, modelPresetOptions, modelBadge, modelBadgeLabel,
  } = useThreadModels({ session, settingsSnapshot, settingsLoading });
  const workspaceOpen = useWorkspaceOpen();
  const historyKey = temporary ? null : session?.key ?? null;
  const previewSessionKey = session?.key ?? null;
  const mentionSessions = useMemo(
    () => sessions.filter((candidate) => candidate.key !== historyKey).map((candidate) => {
      const renamedTitle = titleOverrides[candidate.key]?.trim();
      return renamedTitle ? { ...candidate, title: renamedTitle } : candidate;
    }),
    [historyKey, sessions, titleOverrides],
  );
  const { client, getToken, ingressLimits, token, webuiCapabilities } = useClient();
  const favoriteWorkspaceProject = useCallback(
    async (path: string, pinned: boolean) => {
      const response = await client.requestMutation<{ favorite_projects: ProjectDirectory[] }>("workspace.favorite", { path, pinned });
      return response.favorite_projects;
    },
    [client],
  );
  const resolveWorkspaceProject = useCallback(
    (path: string) => client.requestMutation<ProjectDirectory>("workspace.resolve_project", { path }),
    [client],
  );
  const loadWorkspaceProjects = useCallback(() => fetchWorkspaces(getToken()), [getToken]);
  const browseWorkspaceDirectories = useCallback(
    (path: string, query: string, showHidden: boolean, allowPartial = false) =>
      fetchWorkspaceDirectories(getToken(), path, query, showHidden, allowPartial),
    [getToken],
  );
  const [booting, setBooting] = useState(false);
  const [slashCommands, setSlashCommands] = useState<SlashCommand[]>([]);
  const [mentionCatalogRequestCount, setMentionCatalogRequestCount] = useState(0);
  const requestMentionCatalogs = useCallback(() => setMentionCatalogRequestCount((count) => count + 1), []);
  const { items: cliApps, error: cliAppsError } = useInstalledSettingItems({
    requestCount: mentionCatalogRequestCount,
    getToken,
    eventName: CLI_APPS_CHANGED_EVENT,
    fetchPayload: fetchInstalledCliApps,
    isPayload: isCliAppsPayload,
    selectItems: installedCliAppsFromPayload,
  });
  const { items: mcpPresets, error: mcpPresetsError } = useInstalledSettingItems({
    requestCount: mentionCatalogRequestCount,
    getToken,
    eventName: MCP_PRESETS_CHANGED_EVENT,
    fetchPayload: fetchMcpPresets,
    isPayload: isMcpPresetsPayload,
    selectItems: installedMcpPresetsFromPayload,
  });
  const [heroGreetingKey, setHeroGreetingKey] = useState(randomHeroGreetingKey);
  const [submittedViewportTurnId, setSubmittedViewportTurnId] = useState<string | null>(null);
  const [pendingForkIndex, setPendingForkIndex] = useState<number | null>(null);
  const draftKey = session?.key ?? (temporaryChatEnabled ? "new:temporary" : "new:chat");
  const persistDraft = session ? !temporary : !temporaryChatEnabled;
  const [quote, setQuote] = useState<{ key: string; text: string | null } | null>(null);
  const quotedContext = quote?.key === draftKey
    ? quote.text
    : draftStore?.get(draftKey, persistDraft)?.quotedContext ?? null;
  const setQuotedContext = useCallback((text: string | null) => {
    setQuote({ key: draftKey, text });
  }, [draftKey]);
  const [composerFocusSignal, setComposerFocusSignal] = useState(0);
  const [conversationElement, setConversationElement] = useState<HTMLDivElement | null>(null);
  const composerSurfaceRef = useRef<HTMLDivElement | null>(null);
  const pendingFirstRef = useRef<(PendingFirstMessage & { draft?: ComposerDraft; draftKey: string }) | null>(null);
  const [restoredFirstDraft, setRestoredFirstDraft] = useState<{ chatId: string; revision: number; error: string } | null>(null);
  const [pendingFirstTargetChatId, setPendingFirstTargetChatId] = useState<string | null>(null);
  const consumedPendingFirstMessageIdRef = useRef<string | null>(null);
  const viewportRef = useRef<ThreadViewportHandle | null>(null);
  const activeViewportTurnByChatIdRef = useRef<Map<string, string>>(new Map());
  const knownTemporaryChatIdsRef = useRef(new Set<string>());
  const localMessageCacheRef = useRef(new ThreadMessageCache(
    (key) => knownTemporaryChatIdsRef.current.has(key),
  ));
  const messageCacheRef = useRef(messageCache ?? localMessageCacheRef.current);
  messageCacheRef.current = messageCache ?? localMessageCacheRef.current;
  const sessionKeyByChatIdRef = useRef<Map<string, string>>(new Map());
  const handleTurnEnd = useCallback(() => {
    if (chatId) activeViewportTurnByChatIdRef.current.delete(chatId);
    setSubmittedViewportTurnId(null);
    onTurnEnd?.();
  }, [chatId, onTurnEnd]);
  const {
    messages,
    messagesReady,
    isStreaming,
    runStartedAt,
    retryStatus,
    goalState,
    recoveryState,
    continueRecovery,
    send,
    stop,
    history: {
      loading,
      error: historyError,
      loadingOlder,
      olderError,
      hasMoreBefore,
      userMessageOffset,
      hasPendingToolCalls,
      completedTurnIds,
      activeTurnId: historyActiveTurnId,
      version: historyVersion,
      forkBoundaryMessageCount,
    },
    refreshHistory,
    resetHistory,
    loadOlder,
    loadTraceDetails: loadBodyTraceDetails,
    streamError,
    dismissStreamError,
  } = useCirnoStream(
    chatId, undefined, false, handleTurnEnd, undefined, undefined,
    { key: historyKey, cache: messageCacheRef.current },
  );
  const displayMessages = useMemo(() => projectWebuiThreadMessages(messages), [messages]);
  const preview = useThreadPreview({
    chatId, previewSessionKey, workspaceScope, temporary, headerActive,
    filePreviewStore, messageCount: displayMessages.length,
  });
  const { shellRef, previewOpen, fileActions, resolveFilePreviewAvailability, openFilePreview } = preview;
  useEffect(() => setSubmittedViewportTurnId(null), [previewSessionKey]);
  const initialHistoryLoading = loading;
  const showTemporaryChatControl =
    !hideHeader && !session && !loading && !!onTemporaryChatEnabledChange;
  const promptNavigation = usePromptHistory(historyKey, historyVersion, displayMessages);
  const updateNavigationMessages = promptNavigation.updateMessages;
  useEffect(() => {
    if (!chatId || !messagesReady) return;
    messageCacheRef.current.setLoadedMessages(chatId, promptNavigation.window
      ? [displayMessages, promptNavigation.window.messages] : [displayMessages]);
  }, [chatId, messagesReady, displayMessages, promptNavigation.window]);
  useEffect(() => {
    const cache = messageCacheRef.current;
    return () => { if (chatId) cache.deleteLoadedMessages(chatId); };
  }, [chatId]);

  const loadTraceDetails = useCallback(async (refs: string[]) => {
    const details = await loadBodyTraceDetails(refs);
    for (const detail of details) {
      const projected = projectThreadEvents(detail.events);
      updateNavigationMessages((current) => current.flatMap((message) => (
        message.traceDetail?.ref === detail.ref
          ? projected.map((row) => ({ ...row, activitySegmentId: message.activitySegmentId }))
          : [message]
      )));
    }
  }, [loadBodyTraceDetails, updateNavigationMessages]);

  useEffect(() => {
    if (chatId && historyKey) sessionKeyByChatIdRef.current.set(chatId, historyKey);
  }, [chatId, historyKey]);

  useEffect(() => {
    const retained = new Set(temporaryChatIds);
    for (const chatId of retained) knownTemporaryChatIdsRef.current.add(chatId);
    for (const cachedChatId of knownTemporaryChatIdsRef.current) {
      if (!retained.has(cachedChatId)) {
        // Shared caches are retained/pruned by the app, not by individual panes.
        if (!messageCache) messageCacheRef.current.delete(cachedChatId);
        activeViewportTurnByChatIdRef.current.delete(cachedChatId);
        knownTemporaryChatIdsRef.current.delete(cachedChatId);
      }
    }
  }, [messageCache, temporaryChatIds]);

  const handleQuoteSelection = useCallback((text: string) => {
    setQuotedContext(text);
    setComposerFocusSignal((value) => value + 1);
  }, [setQuotedContext]);

  const hasAppMentions = displayMessages.some((message) => message.cliApps?.length || message.mcpPresets?.length);
  useEffect(() => {
    if (hasAppMentions) requestMentionCatalogs();
  }, [hasAppMentions, requestMentionCatalogs]);
  const { composerContextUsage, composerContextError, composerRoundUsage } = useThreadUsage(
    displayMessages, previewSessionKey, isStreaming,
  );
  const { beginMessageEdit, editBusy, messageEditor } = useMessageEditing({
    sessionKey: session?.key ?? null, displayMessages, turnActive: messagesReady && isStreaming, resetHistory,
  });
  const currentGoalState = messagesReady ? goalState : undefined;
  // Recovery decisions gate queued input, not the ledger-owned run state.
  const recoveryNeedsDecision = recoveryState?.status === "awaiting_user"
    || recoveryState?.status === "failed";
  const recoveryFailure = recoveryState?.reason === "model_request_failed"
    ? resolveModelRequestFailureCopy({ errorKind: recoveryState.failure_error_kind }, t)
    : null;
  const currentRunStartedAt = messagesReady ? runStartedAt : null;
  const turnActive = messagesReady && isStreaming;
  const restoredViewportTurnId = useMemo(
    () => turnActive ? latestActiveTurnId(displayMessages, currentRunStartedAt) : null,
    [currentRunStartedAt, displayMessages, turnActive],
  );
  const rememberedViewportTurnId = chatId
    ? activeViewportTurnByChatIdRef.current.get(chatId) ?? null
    : null;
  const canonicalRunTurnId = chatId && messagesReady && turnActive
    ? client.getRunTurnId(chatId)
    : null;
  const viewportTurnId = messagesReady && turnActive
    ? canonicalRunTurnId
    ?? rememberedViewportTurnId
    ?? historyActiveTurnId
    ?? restoredViewportTurnId
    : null;
  const activeTurnStartedHere =
    viewportTurnId !== null && viewportTurnId === submittedViewportTurnId;
  useEffect(() => {
    if (!chatId || !messagesReady || turnActive) return;
    activeViewportTurnByChatIdRef.current.delete(chatId);
    setSubmittedViewportTurnId((current) =>
      current === rememberedViewportTurnId ? null : current,
    );
  }, [chatId, messagesReady, rememberedViewportTurnId, turnActive]);
  const showHeroComposer = displayMessages.length === 0 && !initialHistoryLoading && !historyError;
  const composerVariant = showHeroComposer ? emptyComposerVariant : "thread";
  // Only unpersisted drafts can choose a project; history pages do not own this state.
  const projectLocked = !!session && session.projectLocked !== false;
  const wasShowingHeroComposerRef = useRef(showHeroComposer);
  const availableSlashCommands = useMemo(
    () => temporary && session
      ? slashCommands.filter(({ command }) => command === "/model" || command === "/stop")
      : slashCommands.filter(({ command }) => (!session || !["/ptc", "/temporary"].includes(command))
        && (command !== "/clear" || conversationRole(session?.key).toolReplies)),
    [slashCommands, temporary, session?.key],
  );
  useEffect(() => {
    if (showHeroComposer && !wasShowingHeroComposerRef.current) {
      setHeroGreetingKey(randomHeroGreetingKey());
    }
    wasShowingHeroComposerRef.current = showHeroComposer;
  }, [showHeroComposer]);

  const withWorkspaceScope = useCallback(
    (options?: SendOptions): SendOptions | undefined => {
      if (!workspaceScope) return options;
      return {
        ...(options ?? {}),
        workspaceScope,
      };
    },
    [workspaceScope],
  );

  const lastRunTurnId = chatId ? client.getRunTurnId(chatId) : null;
  const completedRunTurnId = chatId && lastRunTurnId && client.isRunCompleted(chatId, lastRunTurnId)
    ? lastRunTurnId : null;
  const queueCompletedTurnIds = useMemo(() => {
    const canonical = hasPendingToolCalls ? [] : completedTurnIds;
    // Live terminal facts can release the queue before the history refresh finishes.
    return completedRunTurnId && !canonical.includes(completedRunTurnId)
      ? [...canonical, completedRunTurnId] : canonical;
  }, [completedTurnIds, completedRunTurnId, hasPendingToolCalls]);

  useEffect(() => {
    if (!historyKey || !chatId) return;
    return client.onSessionUpdate((updatedChatId, scope) => {
      if (updatedChatId !== chatId) return;
      if (scope === "metadata") return;
      if (scope === "reset") { resetHistory(); return; }
      // A turn-end thread refresh can arrive while the viewport is easing the
      // final layout change. User-driven scrolling already disables following,
      // so keep an active programmatic follow alive across canonical hydration.
      refreshHistory();
    });
  }, [chatId, client, historyKey, refreshHistory, resetHistory]);

  const wasPageHiddenRef = useRef(document.visibilityState === "hidden");
  useEffect(() => {
    const refreshOnReturn = () => {
      if (document.visibilityState === "hidden") {
        wasPageHiddenRef.current = true;
        return;
      }
      if (!wasPageHiddenRef.current) return;
      wasPageHiddenRef.current = false;
      if (!historyKey || !chatId || client.status !== "open" || loading) return;
      if (
        !turnActive
        && !hasPendingToolCalls
        && !client.hasUnsettledRun(chatId)
        && !historyError
      ) {
        return;
      }
      refreshHistory();
    };
    document.addEventListener("visibilitychange", refreshOnReturn);
    return () => document.removeEventListener("visibilitychange", refreshOnReturn);
  }, [
    chatId,
    client,
    hasPendingToolCalls,
    historyKey,
    historyError,
    loading,
    refreshHistory,
    turnActive,
  ]);

  useEffect(() => {
    let refreshOnNextOpen = client.status !== "open";
    return client.onStatus((status) => {
      if (status !== "open") {
        refreshOnNextOpen = true;
        return;
      }
      if (refreshOnNextOpen) refreshHistory();
      refreshOnNextOpen = false;
    });
  }, [client, refreshHistory]);

  // The landing composer queues the first message while `new_chat` is in flight.
  // Only the chat created for that send may consume it; selecting another chat
  // while creation is pending must not leak the message there.
  useEffect(() => {
    if (!chatId || pendingFirstTargetChatId !== chatId) return;
    const pending = pendingFirstRef.current;
    if (!pending) {
      setPendingFirstTargetChatId(null);
      return;
    }
    pendingFirstRef.current = null;
    setPendingFirstTargetChatId(null);
    const submitted = send(pending.content, pending.images, pending.options);
    if (submitted && !submitted.sideChannel) {
      activeViewportTurnByChatIdRef.current.set(chatId, submitted.turnId);
      setSubmittedViewportTurnId(submitted.turnId);
    }
    if (submitted?.delivery) {
      void submitted.delivery.then(() => pending.finish?.(true), (error: unknown) => {
        // Topic creation already unmounted the landing composer. A rejected
        // local reference must hand its draft to that topic, not strand it on /new.
        if (pending.draft && pending.images?.some((image) => image.media.path !== undefined)) {
          const targetKey = `websocket:${chatId}`;
          const current = draftStore?.get(targetKey, !temporary);
          if (!current?.text && !current?.attachments.length
            && !current?.sessionMentions.length && !current?.quotedContext) {
            draftStore?.set(targetKey, pending.draft, !temporary);
            if (draftStore?.get(pending.draftKey) === pending.draft) draftStore.delete(pending.draftKey);
            setRestoredFirstDraft((previous) => ({
              chatId, revision: (previous?.revision ?? 0) + 1,
              error: error instanceof Error ? error.message : String(error),
            }));
          }
        }
        pending.finish?.(false);
      });
    } else pending.finish?.(submitted !== null);
    setBooting(false);
  }, [chatId, draftStore, pendingFirstTargetChatId, send, temporary]);

  useEffect(() => {
    if (
      !chatId
      || pendingFirstMessage?.chatId !== chatId
      || consumedPendingFirstMessageIdRef.current === pendingFirstMessage.id
    ) return;
    consumedPendingFirstMessageIdRef.current = pendingFirstMessage.id;
    const submitted = send(
      pendingFirstMessage.content,
      pendingFirstMessage.images,
      withWorkspaceScope(pendingFirstMessage.options),
    );
    if (submitted && !submitted.sideChannel) {
      activeViewportTurnByChatIdRef.current.set(chatId, submitted.turnId);
      setSubmittedViewportTurnId(submitted.turnId);
    }
    onPendingFirstMessageConsumed?.(pendingFirstMessage.id);
  }, [
    chatId,
    onPendingFirstMessageConsumed,
    pendingFirstMessage,
    send,
    withWorkspaceScope,
  ]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const commands = await listSlashCommands(getToken());
        if (!cancelled) setSlashCommands(commands);
      } catch {
        if (!cancelled) setSlashCommands([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [getToken]);

  const [controlError, setControlError] = useState("");
  const handleComposerControl = useCallback((content: string): boolean | null => {
    const [rawName, ...parts] = content.trim().split(/\s+/);
    const name = rawName.toLowerCase();
    const argument = parts.join(" ").toLowerCase();
    if (!["/temporary", "/ptc", "/access", ...(!session ? ["/model"] : [])].includes(name.toLowerCase())) return null;
    setControlError("");
    if (turnActive || hasPendingToolCalls) { setControlError(t("thread.composer.slash.controlRunning")); return false; }
    if (name === "/access") {
      const mode = ({ default: "restricted", restricted: "restricted", review: "review", full: "full" } as const)[argument as "default" | "restricted" | "review" | "full"];
      if (!mode || !workspaceScope || !onWorkspaceScopeChange) { setControlError(t("thread.composer.slash.accessUsage")); return false; }
      onWorkspaceScopeChange(scopeWithAccessMode(workspaceScope, mode)); return true;
    }
    if (name === "/model" && !argument) return null;
    if (name === "/model") {
      const selected = resolveModelPresetSelection(settings, parts.join(" "));
      if (!selected) { setControlError(t("thread.composer.slash.modelUsage")); return false; }
      handleModelPresetChange(selected); return true;
    }
    const change = name === "/ptc" ? onPtcModeEnabledChange : onTemporaryChatEnabledChange;
    if (session || !change) { setControlError(t("thread.composer.slash.creationOnly")); return false; }
    if (argument !== "on" && argument !== "off") { setControlError(t("thread.composer.slash.toggleUsage", { command: name })); return false; }
    change(argument === "on"); return true;
  }, [session, turnActive, hasPendingToolCalls, t, workspaceScope, onWorkspaceScopeChange, settings, handleModelPresetChange, onPtcModeEnabledChange, onTemporaryChatEnabledChange]);

  const handleWelcomeSend = useCallback(
    async (content: string, images?: SendAttachment[], options?: SendOptions) => {
      const control = handleComposerControl(content);
      if (control !== null) return control;
      if (booting) return false;
      setBooting(true);
      let finish!: (accepted: boolean) => void;
      const delivery = new Promise<boolean>((resolve) => { finish = resolve; });
      pendingFirstRef.current = {
        content, images, options: withWorkspaceScope(options), finish,
        draftKey, draft: draftStore?.get(draftKey, persistDraft),
      };
      setPendingFirstTargetChatId(null);
      const newId = await onCreateChat?.(workspaceScope, content, localModelPreset);
      if (!newId) {
        pendingFirstRef.current = null;
        setPendingFirstTargetChatId(null);
        setBooting(false);
        return false;
      }
      setPendingFirstTargetChatId(newId);
      return delivery;
    },
    [handleComposerControl, booting, client, draftKey, draftStore, localModelPreset, onCreateChat, persistDraft, withWorkspaceScope, workspaceScope],
  );

  const inspectAttachment = useCallback(async (path: string) => {
    const result = await client.requestMutation("attachment.inspect", {
      chat_id: chatId, path, ...(workspaceScope ? { workspace_scope: workspaceScope } : {}),
    });
    if (!isLocalAttachment(result)) throw new Error("Invalid attachment metadata");
    return result;
  }, [chatId, client, workspaceScope]);

  const handleThreadSend = useCallback(
    (content: string, images?: SendAttachment[], options?: SendOptions) => {
      const control = handleComposerControl(content);
      if (control !== null) return control;
      setRestoredFirstDraft((current) => current?.chatId === chatId ? { ...current, error: "" } : current);
      const submitted = send(content, images, withWorkspaceScope(options));
      if (
        chatId
        && submitted
        && !submitted.sideChannel
        && options?.continueActiveTurn !== true
      ) {
        activeViewportTurnByChatIdRef.current.set(chatId, submitted.turnId);
        setSubmittedViewportTurnId(submitted.turnId);
      }
      return submitted?.delivery ? submitted.delivery.then(() => true) : submitted !== null;
    },
    [handleComposerControl, chatId, send, withWorkspaceScope],
  );

  const answerQuestion = useCallback((question: UserQuestion, answer: string) =>
    handleThreadSend(formatQuestionAnswer(question, answer), undefined,
      turnActive ? { continueActiveTurn: true } : undefined), [handleThreadSend, turnActive]);

  const forkFromSavedContext = useCallback(
    async (beforeUserIndex: number) => {
      if (!chatId || !onForkChat || !conversationRole(session?.key).canFork) return;
      const forkedChatId = await onForkChat(chatId, beforeUserIndex);
      if (!forkedChatId) return;
      messageCacheRef.current.delete(forkedChatId);
    },
    [chatId, onForkChat, session?.key],
  );
  const handleForkFromMessage = useCallback((index: number) => {
    if (displayMessages.some(hasToolHistory)) {
      setPendingForkIndex(index);
    } else {
      void forkFromSavedContext(index);
    }
  }, [displayMessages, forkFromSavedContext]);
  useEffect(() => setPendingForkIndex(null), [chatId]);

  const composer = (
    <div className={composerVariant === "hero" ? "thread-composer-stack is-hero" : "thread-composer-stack"}>
      {modelFallback?.chatId === chatId && !modelFallback.dismissed ? (
        <ModelFallbackNotice
          model={modelFallback.model}
          reauthProvider={modelFallback.reauthProvider}
          reauthProviderLabel={modelFallback.reauthProvider
            ? providerDisplayLabel(settings?.providers ?? [], modelFallback.reauthProvider)
            : undefined}
          onOpenSettings={onOpenModelSettings}
          onDismiss={() => setModelFallback((current) => current && { ...current, dismissed: true })}
        />
      ) : null}
      {recoveryNeedsDecision && !turnActive ? (
        <p role={recoveryFailure ? "alert" : "status"} className="thread-composer-inline-status px-3 text-xs text-muted-foreground">
          {recoveryFailure ? `${recoveryFailure.title} ${recoveryFailure.body}` : recoveryState?.can_continue === false
            ? t("recovery.failedHelp")
            : t("recovery.interrupted")}
        </p>
      ) : null}
      {streamError && !hasInlineDeliveryError(messages, streamError) ? (
        <StreamErrorNotice
          error={streamError}
          onDismiss={dismissStreamError}
          onOpenSettings={onOpenModelSettings}
        />
      ) : null}
      {restoredFirstDraft?.chatId === chatId && restoredFirstDraft.error ? (
        <p role="alert" className="px-3 text-sm text-destructive">{restoredFirstDraft.error}</p>
      ) : null}
      <SubagentTaskDock inputKey={latestSubagentInputKey(displayMessages)} />
      {controlError && <p role="alert" className="px-3 text-sm text-destructive">{controlError}</p>}
      {(cliAppsError || mcpPresetsError) && <p role="status" className="px-3 text-sm text-destructive">{[cliAppsError, mcpPresetsError].filter(Boolean).join("; ")}</p>}
      {modelSettingsError && <p role="status" className="px-3 text-sm text-destructive">{modelSettingsError}</p>}
      {modelPresetError && <p role="alert" className="px-3 text-sm text-destructive">{modelPresetError}</p>}
      <UserQuestionQueue isStreaming={turnActive} onStop={stop}>
        <ThreadComposer
          active={composerActive}
          key={session ? `${draftKey}:${restoredFirstDraft?.chatId === chatId ? restoredFirstDraft.revision : 0}` : draftKey}
          draftKey={draftKey}
          draftStore={draftStore}
          persistDraft={persistDraft}
          onSend={session ? handleThreadSend : handleWelcomeSend}
          disabled={session ? !chatId : booting}
          inputAriaLabel={composerInputAriaLabel}
          isStreaming={turnActive}
          activeTurnId={session && turnActive && chatId ? client.getRunTurnId(chatId) ?? historyActiveTurnId : null}
          completedTurnIds={session && messagesReady && !recoveryNeedsDecision && chatId && !client.hasUnsettledRun(chatId) ? queueCompletedTurnIds : undefined}
          placeholder={!session && booting ? t("thread.composer.placeholderOpening") : composerVariant === "hero" || !session ? t("thread.composer.placeholderHero") : t("thread.composer.placeholderThread")}
          modelLabel={modelBadgeLabel}
          modelDetail={modelBadge.model}
          modelPreset={activeModelPreset}
          modelPresets={modelPresetOptions}
          onModelPresetChange={handleModelPresetChange}
          modelProvider={modelBadge.provider}
          modelProviderLabel={modelBadge.providerLabel}
          modelNeedsSetup={modelBadge.needsSetup}
          onModelBadgeClick={modelBadge.needsSetup ? onOpenModelSettings : undefined}
          onManageModels={onOpenModelSettings}
          showContextUsage={session !== null}
          contextUsage={composerContextUsage}
          contextUsageError={composerContextError}
          recentRoundUsage={composerRoundUsage}
          variant={session ? composerVariant : "hero"}
          slashCommands={availableSlashCommands}
          onMentionSearch={requestMentionCatalogs}
          cliApps={cliApps}
          mcpPresets={mcpPresets}
          sessions={mentionSessions}
          skills={skills}
          onStop={session ? stop : undefined}
          onContinue={session && recoveryNeedsDecision && recoveryState?.can_continue !== false && !turnActive ? continueRecovery : undefined}
          onInspectAttachment={inspectAttachment}
          goalState={currentGoalState}
          onFavoriteWorkspaceProject={favoriteWorkspaceProject}
          onResolveWorkspaceProject={resolveWorkspaceProject}
          onLoadWorkspaceProjects={loadWorkspaceProjects}
          workspacePickerLayoutAnchor={conversationElement}
          onBrowseWorkspaceDirectories={browseWorkspaceDirectories}
          workspaceScope={workspaceScope}
          workspaceControlsHidden={temporary}
          workspaceDefaultScope={workspaceDefaultScope}
          workspaceControls={workspaceControls}
          workspaceScopeDisabled={workspaceScopeDisabled}
          workspaceProjectLocked={projectLocked}
          workspaceError={workspaceError}
          onWorkspaceScopeChange={onWorkspaceScopeChange}
          pendingQueueKey={session && !temporary ? chatId : null}
          ingressLimits={ingressLimits}
          quotedContext={quotedContext}
          focusRequest={session ? composerFocusSignal : undefined}
          onQuotedContextChange={setQuotedContext}
          surfaceRef={session ? undefined : composerSurfaceRef}
        />
      </UserQuestionQueue>
    </div>
  );

  const emptyState = historyError ? null : initialHistoryLoading ? (
    <ThreadLoadingSkeleton />
  ) : (
    <div className="flex w-full flex-col items-center text-center animate-in fade-in-0 slide-in-from-bottom-2 [animation-duration:220ms] motion-reduce:animate-none">
      <HeroGreeting text={t(heroGreetingKey)} />
    </div>
  );
  const sessionInfoAction = historyKey ? (
    <SessionAutomations client={client} sessionKey={historyKey} token={token} title={title} />
  ) : undefined;
  const promptNavigatorAction = historyKey ? (
    <PromptNavigator
      messages={displayMessages}
      prompts={promptNavigation.prompts}
      source={promptNavigation.source}
      onJumpToPrompt={(promptId) => viewportRef.current?.jumpToUserPrompt(promptId)}
    />
  ) : undefined;

  const threadHeader = !hideHeader ? (
    <ThreadHeader
      className={previewOpen ? "h-10" : undefined}
      title={title}
      onToggleSidebar={onToggleSidebar}
      theme={theme}
      onToggleTheme={onToggleTheme}
      hideDesktopSidebarToggle={hideDesktopSidebarToggle}
      hideSidebarToggle={hideSidebarToggle}
      hideThemeButton={hideThemeButton}
      hideTitle={hideHeaderTitle}
      actions={<>{session && conversationRole(session.key).name === "router" && <RouterHeartbeatButton client={client} />}{headerActions}{workspaceOpen && previewSessionKey && !temporary && <HoverHint content={t("workspace.trace")}><Button type="button" variant="ghost" size="icon" className={headerControlClassName} aria-label={t("workspace.trace")} onClick={() => workspaceOpen("trace", { sessionKey: previewSessionKey, scope: workspaceScope })}><Route className="h-4 w-4" /></Button></HoverHint>}{session && conversationRole(session.key).toolReplies && <ClearConversationButton client={client} chatId={session.chatId} onCleared={resetHistory} />}<HoverHint content={t("files.title")}><Button type="button" variant="ghost" size="icon" className={headerControlClassName} aria-label={t("files.title")}
        onClick={preview.openFiles}><FolderOpen className="h-4 w-4" /></Button></HoverHint></>}
      minimal={!session && !loading}
      promptNavigatorAction={promptNavigatorAction}
      sessionInfoAction={sessionInfoAction}
      ptcModeEnabled={session?.ptcMode ?? ptcModeEnabled}
      onPtcModeEnabledChange={!session && !loading ? onPtcModeEnabledChange : undefined}
      temporaryChatEnabled={temporaryChatEnabled}
      temporaryChatDisabled={booting || turnActive}
      onTemporaryChatEnabledChange={
        showTemporaryChatControl ? onTemporaryChatEnabledChange : undefined
      }
    />
  ) : null;

  return (
    <SubagentTasksProvider client={client} token={token}
      sessionKey={session?.key ?? null}
      liveEvents={webuiCapabilities.includes("webui.subagents.events.v1")}
      historyEnabled={webuiCapabilities.includes("webui.subagents.history.v1")}
      active={composerActive}
      enabled={!temporary && !!session?.key.startsWith("websocket:") && webuiCapabilities.includes("webui.subagents.v1")}>
      <QuestionReplyProvider messages={displayMessages} send={messagesReady ? answerQuestion : undefined}>
        <section ref={shellRef} data-preview-open={previewOpen || undefined} className="thread-preview-layout relative flex min-h-0 flex-1 overflow-hidden">
          <div ref={setConversationElement} className={cn(
            "thread-conversation relative flex min-w-0 flex-1 flex-col overflow-hidden",
            headerPortalTarget === undefined && !hideHeader && "thread-workspace",
          )}>
            {hideHeaderTitle && inlineHandle && !temporary && session?.handle ? (
              <div
                aria-label={`Session @${session.handle.name}`}
                className="flex h-8 shrink-0 items-center px-3 text-[12px]"
              >
                <span
                  className="shrink-0"
                >
                  <SessionHandleLabel id={session.handle.id}>
                    @{session.handle.name}
                  </SessionHandleLabel>
                </span>
              </div>
            ) : null}
            {headerPortalTarget === undefined ? threadHeader : null}
            {historyError && <div role="alert" className="flex shrink-0 items-center justify-between gap-3 border-b border-destructive/30 bg-destructive/5 px-4 py-3 text-sm">
              <span className="min-w-0 break-words">{historyError}</span>
              <Button variant="ghost" size="sm" className="shrink-0" onClick={refreshHistory}>{t("thread.history.retryLabel")}</Button>
            </div>}
            <FilePreviewAvailabilityProvider
              resolve={previewSessionKey ? resolveFilePreviewAvailability : undefined}
            >
              <FileActionsProvider value={previewSessionKey ? fileActions : undefined}>
                <ThreadViewport
                  ref={viewportRef}
                  messages={displayMessages}
                  navigation={promptNavigation}
                  navigationFrame={navigationFrame}
                  temporary={temporary}
                  isStreaming={turnActive}
                  runStartedAt={currentRunStartedAt}
                  retryStatus={retryStatus}
                  emptyState={emptyState}
                  initialLoading={initialHistoryLoading}
                  composer={composerPortalTarget === undefined ? composer : null}
                  activeTurnId={viewportTurnId}
                  activeTurnStartedHere={activeTurnStartedHere}
                  conversationKey={historyKey}
                  conversationReady={messagesReady}
                  showScrollToBottomButton={!!session}
                  cliApps={cliApps}
                  mcpPresets={mcpPresets}
                  slashCommands={availableSlashCommands}
                  forkBoundaryMessageCount={forkBoundaryMessageCount}
                  hasMoreBefore={hasMoreBefore}
                  loadingOlder={loadingOlder}
                  olderError={olderError}
                  userMessageOffset={userMessageOffset}
                  onLoadOlder={loadOlder}
                  traceDetailScope={historyKey}
                  onLoadTraceDetails={messagesReady ? loadTraceDetails : undefined}
                  onOpenFilePreview={previewSessionKey ? openFilePreview : undefined}
                  onForkFromMessage={onForkChat && conversationRole(session?.key).canFork ? handleForkFromMessage : undefined}
                  onEditMessage={!temporary && !editBusy ? beginMessageEdit : undefined}
                  messageEditor={messageEditor}
                  onQuoteSelection={session ? handleQuoteSelection : undefined}
                />
              </FileActionsProvider>
            </FilePreviewAvailabilityProvider>
          </div>
          {headerPortalTarget && headerActive
            ? createPortal(threadHeader, headerPortalTarget)
            : null}
          {composerPortalTarget ? createPortal(
            <div
              hidden={!composerActive}
              aria-hidden={!composerActive}
              data-testid={composerActive ? "active-pane-composer" : undefined}
            >
              {composer}
            </div>,
            composerPortalTarget,
          ) : null}
          <ThreadPreview controller={preview} />
        </section>
        <AlertDialog open={pendingForkIndex !== null} onOpenChange={open => { if (!open) setPendingForkIndex(null); }}>
          <AlertDialogContent data-history-effects-warning>
            <AlertDialogHeader><AlertDialogTitle>{t("thread.historyEffects.title")}</AlertDialogTitle>
              <AlertDialogDescription className="text-destructive">{t("thread.historyEffects.description")}</AlertDialogDescription></AlertDialogHeader>
            <AlertDialogFooter><AlertDialogCancel>{t("files.cancel")}</AlertDialogCancel>
              <AlertDialogAction onClick={() => { if (pendingForkIndex !== null) void forkFromSavedContext(pendingForkIndex); setPendingForkIndex(null); }}>{t("message.forkFromHere")}</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </QuestionReplyProvider>
    </SubagentTasksProvider>
  );
}
