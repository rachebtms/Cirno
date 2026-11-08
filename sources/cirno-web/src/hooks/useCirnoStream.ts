import { useStreamBuffer } from "./stream/useStreamBuffer";
import { acceptsCompactionPhase } from "../../packages/client-events/notifications";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useThreadVisibility } from "@/hooks/useThreadVisibility";

import { useClient } from "@/providers/ClientProvider";
import { hasPendingAgentActivity } from "@/lib/activity-timeline";
import { ApiError, fetchWebuiThread, fetchWebuiThreadTraceDetail } from "@/lib/api";
import { fetchLatestWebuiThread } from "@/lib/latest-thread-request";
import { persistedCanonicalRunState } from "@/lib/canonical-run-snapshot";
import { webuiThreadCache } from "@/lib/webui-thread-cache";
import { ThreadTranscript, type ThreadPaging, type ThreadRead, type ThreadTranscriptSnapshot } from "@/lib/thread-transcript";
import type { ThreadMessageCache } from "@/lib/thread-message-cache";
import type { StreamError } from "@/lib/cirno-client";
import {
  appendProjectedSessionInput,
  transitionTurnDelivery,
  clearThreadProjectionActivity,
  closeThreadProjectionAnswer,
  finalizeStreamedTurn,
  resetThreadProjectionCursor,
  turnFieldsFromEvent,
} from "@/lib/thread-event-projection";
import type {
  ThreadProjectionEvent,
} from "@/lib/thread-event-projection";
import { formatQuotedUserMessage } from "@/lib/user-message-quote";
import { playTurnCompleteSound } from "@/lib/notification-sound";
import type { InboundEvent, RecoveryState } from "@/lib/contracts/events";
import type { OutboundCliAppMention, OutboundMcpPresetMention, OutboundMedia, SessionMention, RetryStatus, UIMediaAttachment, UIMessage } from "@/lib/contracts/messages";
import type { GoalStateWsPayload } from "@/lib/contracts/activity";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";

const EMPTY_INITIAL_MESSAGES: UIMessage[] = [];
const EMPTY_COMPLETED_TURN_IDS: readonly string[] = [];

/** Own the received transcript, accepting fetched pages and live events together. */
/** Payload passed to ``send`` when the user attaches one or more files.
 *
 * ``media`` is handed to the wire client verbatim; ``preview`` powers the
 * optimistic user bubble. Keeping the two separate lets the bubble re-use the
 * local data URL even after the server persists the file under a different
 * name. */
export interface SendAttachment {
  media: OutboundMedia;
  preview: UIMediaAttachment;
}

export interface SendOptions {
  intent?: "create_automation";
  cliApps?: OutboundCliAppMention[];
  mcpPresets?: OutboundMcpPresetMention[];
  sessionMentions?: SessionMention[];
  quotedContext?: string;
  workspaceScope?: WorkspaceScopePayload | null;
  sideChannel?: boolean;
  userShell?: boolean;
  finalizeActiveTurn?: boolean;
  /** Append guidance to the running turn without detaching its active answer segment. */
  continueActiveTurn?: boolean;
}

export interface SubmittedTurn {
  delivery?: Promise<void>;
  turnId: string;
  userMessageId: string;
  sideChannel: boolean;
}

function eventTurnId(ev: InboundEvent): string | undefined {
  return "turn_id" in ev && typeof ev.turn_id === "string" ? ev.turn_id : undefined;
}

function createTranscript(messages: UIMessage[], saved: ThreadTranscriptSnapshot | undefined, historyKey: string | null) {
  const owner = new ThreadTranscript(messages, saved);
  // The first paint must not enter the welcome layout while history is pending.
  owner.paging = { ...owner.paging, loading: !!historyKey && owner.paging.version === 0 };
  return owner;
}

export function useCirnoStream(
  chatId: string | null,
  initialMessages: UIMessage[] = EMPTY_INITIAL_MESSAGES,
  hasPendingToolCalls = false,
  onTurnEnd?: () => void,
  onStreamDetach?: (messages: UIMessage[]) => void,
  completedTurnIds: readonly string[] = EMPTY_COMPLETED_TURN_IDS,
  history?: { key: string | null; cache?: ThreadMessageCache },
  historyActiveTurnId: string | null = null,
): {
  messages: UIMessage[];
  /** Whether ``messages`` belongs to the current ``chatId`` after a session switch. */
  messagesReady: boolean;
  isStreaming: boolean;
  /** Unix epoch seconds when the current user turn started (WebSocket ``goal_status``). */
  runStartedAt: number | null;
  /** Transient model retry state for the active turn. */
  retryStatus: RetryStatus | null;
  /** Latest sustained goal for this ``chatId`` (``goal_state`` WS events). */
  goalState: GoalStateWsPayload | undefined;
  recoveryState: RecoveryState | null;
  continueRecovery: () => Promise<void>;
  dismissRecovery: () => Promise<void>;
  send: (
    content: string,
    images?: SendAttachment[],
    options?: SendOptions,
  ) => SubmittedTurn | null;
  stop: () => Promise<void>;
  history: ThreadPaging;
  refreshHistory: () => void;
  resetHistory: (keepTurnId?: string) => void;
  loadOlder: () => Promise<void>;
  loadTraceDetails: (refs: string[]) => Promise<Array<{ ref: string; events: ThreadProjectionEvent[] }>>;
  /** Latest transport-level fault raised since the last ``dismissStreamError``.
   * ``null`` when there is nothing to show. */
  streamError: StreamError | null;
  /** Clear the current ``streamError`` (e.g. after the user dismisses the
   * notification or starts a fresh action). */
  dismissStreamError: () => void;
} {
  const { client, getToken } = useClient();
  const historyKey = history?.key ?? null;
  const messageCache = history?.cache;
  const [initialTranscript] = useState(() => createTranscript(initialMessages,
    chatId ? messageCache?.get(chatId) : undefined, historyKey));
  const transcriptRef = useRef(initialTranscript);
  const [historyState, setHistoryState] = useState(initialTranscript.paging);
  const publishHistory = useCallback(() => setHistoryState(transcriptRef.current.paging), []);
  const [refreshSeq, setRefreshSeq] = useState(0);
  const latestReadRef = useRef<AbortController | undefined>(undefined);
  const latestRefreshQueued = useRef(false);
  const refreshHistory = useCallback(() => {
    if (latestReadRef.current) {
      latestRefreshQueued.current = true;
      return;
    }
    setRefreshSeq((value) => value + 1);
  }, []);
  useEffect(() => {
    let connected = client.status === "open";
    const unsubscribe = client.onStatus(status => {
      if (status === "open" && !connected && historyKey) refreshHistory();
      connected = status === "open";
    });
    const onPageShow = (event: PageTransitionEvent) => { if (event.persisted && historyKey) refreshHistory(); };
    window.addEventListener("pageshow", onPageShow);
    return () => { unsubscribe(); window.removeEventListener("pageshow", onPageShow); };
  }, [client, historyKey, refreshHistory]);
  const threadVisible = useThreadVisibility();
  const [runState, setRunState] = useState(() => chatId ? client.getRunState(chatId) : null);
  const isStreaming = runState?.active ?? false;
  const runStartedAt = runState?.startedAt ?? null;
  const historyRunGenerationRef = useRef({ chatId, generation: chatId ? client.getRunGeneration(chatId) : 0 });
  if (historyRunGenerationRef.current.chatId !== chatId) {
    historyRunGenerationRef.current = { chatId, generation: chatId ? client.getRunGeneration(chatId) : 0 };
  }
  const [messages, setRenderedMessages] = useState<UIMessage[]>(initialTranscript.messages);
  const messagesRef = useRef(messages);
  // Keep received state ahead of React's batched render: navigation can unmount
  // this hook after a stream flush but before the queued render commits.
  const setMessages = useCallback<React.Dispatch<React.SetStateAction<UIMessage[]>>>((update) => {
    const next = typeof update === "function" ? update(messagesRef.current) : update;
    messagesRef.current = next;
    transcriptRef.current.projection = { ...transcriptRef.current.projection, messages: next };
    setRenderedMessages(next);
    setHistoryState(transcriptRef.current.paging);
  }, []);
  const [messageScope, setMessageScope] = useState({ chatId, historyKey, client });
  /** If history ends in unfinished agent activity, keep the loading spinner alive. */
  const initialStreaming = useMemo(() => {
    if (completedTurnIds.length === 0) return hasPendingAgentActivity(initialMessages);
    const completedInitialTurns = new Set(completedTurnIds);
    return hasPendingAgentActivity(initialMessages.filter((message) => (
      !message.turnId || !completedInitialTurns.has(message.turnId)
    )));
  }, [completedTurnIds, initialMessages]);
  const [retryStatus, setRetryStatus] = useState<RetryStatus | null>(null);
  const [goalState, setGoalState] = useState<GoalStateWsPayload | undefined>(undefined);
  const [recoveryState, setRecoveryState] = useState<RecoveryState | null>(null);
  const [streamError, setStreamError] = useState<StreamError | null>(null);

  const onForeground = useCallback(() => { if (historyKey) refreshHistory(); }, [historyKey, refreshHistory]);
  const {
    enqueue: enqueueStreamEvent, discardTurn: discardBufferedTurn, snapshot: snapshotStreamEvents,
    flush: flushPendingStreamEvents, clear: clearPendingStreamWork,
  } = useStreamBuffer({ chatId, transcriptRef, setMessages, threadVisible, onForeground });

  const dismissStreamError = useCallback(() => setStreamError(null), []);

  const isSideChannelEvent = useCallback((ev: InboundEvent) => {
    const turnId = eventTurnId(ev);
    return turnId !== undefined && transcriptRef.current.sideChannelTurnIds.has(turnId);
  }, []);

  const clearActivitySegment = useCallback(() => {
    transcriptRef.current.projection = clearThreadProjectionActivity(transcriptRef.current.projection);
  }, []);

  const closeActiveAssistantStream = useCallback(() => {
    const hadActiveAssistant = transcriptRef.current.projection.activeAssistantId !== null;
    transcriptRef.current.projection = closeThreadProjectionAnswer(transcriptRef.current.projection);
    return hadActiveAssistant;
  }, []);

  const applyStreamError = useCallback((err: StreamError) => {
    // One multiplexed client serves every thread. A correlated send fault
    // belongs only to its target chat. An uncorrelated transport close can
    // still be shown in the mounted thread, but cannot roll back any turn.
    if (!chatId || (err.chatId && err.chatId !== chatId)) return;
    setStreamError(err);
    if (err.kind === "model_request_failed") return;
    if (!err.turnId) return;

    const rejectedTurnId = err.turnId;
    discardBufferedTurn(rejectedTurnId);
    transcriptRef.current.sideChannelTurnIds.delete(rejectedTurnId);
    setMessages((prev) => {
      const rejectedRows = prev.filter((message) => message.turnId === rejectedTurnId);
      if (rejectedRows.length === 0) return prev;
      const rejectedIds = new Set(rejectedRows.map((message) => message.id));
      const rejectedSegments = new Set(
        rejectedRows
          .map((message) => message.activitySegmentId)
          .filter((segmentId): segmentId is string => typeof segmentId === "string"),
      );
      const projection = transcriptRef.current.projection;
      const closedAssistantIds = new Set(projection.closedAssistantIds);
      for (const id of rejectedIds) closedAssistantIds.delete(id);
      const nextMessages = prev.flatMap<UIMessage>((message) => {
        if (message.turnId !== rejectedTurnId) return [message];
        if (message.role !== "user") return [];
        return [{
          ...message,
          deliveryStatus: "failed" as const,
          deliveryErrorKind: err.kind,
        }];
      });
      transcriptRef.current.projection = {
        ...projection,
        messages: nextMessages,
        activeAssistantId: projection.activeAssistantId
          && rejectedIds.has(projection.activeAssistantId)
          ? null
          : projection.activeAssistantId,
        closedAssistantIds,
        activitySegmentId: projection.activitySegmentId
          && rejectedSegments.has(projection.activitySegmentId)
          ? null
          : projection.activitySegmentId,
        fileEditSegmentId: projection.fileEditSegmentId
          && rejectedSegments.has(projection.fileEditSegmentId)
          ? null
          : projection.fileEditSegmentId,
      };
      transcriptRef.current.rejectTurn(rejectedTurnId);
      return nextMessages;
    });

    if (!client.getRunState(chatId).active) {
      transcriptRef.current.projection = {
        ...transcriptRef.current.projection,
        suppressUntilTurnEnd: false,
      };
    }
  }, [chatId, client, discardBufferedTurn, setMessages]);

  useEffect(() => client.onError(applyStreamError), [applyStreamError, client]);

  useEffect(() => {
    if (!chatId) return;
    return client.onRunStatus((runChatId, state) => {
      if (runChatId !== chatId) return;
      setRunState(state);
      if (state.active) {
        // A server-confirmed run supersedes the previous interruption, even
        // when a supervisor or another device started it.
        if (state.startedAt !== null) { setRecoveryState(null); setStreamError(null); }
        return;
      }
      flushPendingStreamEvents();
      setMessages((prev) => {
        const settled = prev.map((message) => (
          message.isStreaming ? { ...message, isStreaming: false } : message
        ));
        transcriptRef.current.projection = resetThreadProjectionCursor(
          transcriptRef.current.projection,
          settled,
        );
        return settled;
      });
    });
  }, [chatId, client, clearActivitySegment, flushPendingStreamEvents, setMessages]);

  // Reset local state when switching chats. Do not reset on every
  // ``initialMessages`` update: a brand-new chat can receive an empty/404
  // history response after the optimistic first message has already rendered.
  useEffect(() => {
    transcriptRef.current = createTranscript(initialMessages, chatId ? messageCache?.get(chatId) : undefined, historyKey);
    setMessages(transcriptRef.current.messages);
    setMessageScope({ chatId, historyKey, client });
    setRunState(chatId ? client.getRunState(chatId) : null);
    setStreamError(null);
    setRetryStatus(null);
    setGoalState(chatId ? client.getGoalState(chatId) : undefined);
    setRecoveryState(null);
    clearPendingStreamWork();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatId, client, historyKey, clearActivitySegment, clearPendingStreamWork, setMessages]);

  useEffect(() => {
    if (!chatId || (!hasPendingToolCalls && !initialStreaming)) return;
    client.restorePendingRun(chatId, historyRunGenerationRef.current.generation, historyActiveTurnId);
  }, [chatId, client, hasPendingToolCalls, historyActiveTurnId, initialStreaming]);

  const applyProjectionEvent = useCallback((
    event: ThreadProjectionEvent,
    options?: { sideChannel?: boolean },
  ) => {
    setMessages((prev) => {
      transcriptRef.current.projection = { ...transcriptRef.current.projection, messages: prev };
      return transcriptRef.current.project(event, { createId: () => crypto.randomUUID(), now: Date.now(),
        sideChannel: options?.sideChannel });
    });
  }, [setMessages]);

  const olderReadRef = useRef<{
    owner: ThreadTranscript; read: ThreadRead; controller: AbortController;
  } | null>(null);
  const cancelOlderRead = useCallback(() => {
    const pending = olderReadRef.current;
    if (!pending) return;
    olderReadRef.current = null;
    pending.controller.abort();
    pending.owner.finishRead(pending.read);
    if (transcriptRef.current === pending.owner) publishHistory();
  }, [publishHistory]);
  const resetHistory = useCallback((keepTurnId?: string) => {
    latestReadRef.current?.abort();
    latestReadRef.current = undefined;
    latestRefreshQueued.current = false;
    flushPendingStreamEvents();
    cancelOlderRead();
    const retained = keepTurnId ? transcriptRef.current.messages.filter(message => message.turnId === keepTurnId) : [];
    const owner = new ThreadTranscript(retained, undefined, true);
    owner.paging = { ...owner.paging, loading: Boolean(historyKey) };
    transcriptRef.current = owner;
    setMessages(owner.messages);
    setGoalState(undefined); setRecoveryState(null); setRetryStatus(null); setStreamError(null);
    if (chatId) messageCache?.set(chatId, owner.save());
    if (historyKey) webuiThreadCache.delete(historyKey);
    setRefreshSeq((value) => value + 1);
  }, [chatId, historyKey, messageCache, flushPendingStreamEvents, cancelOlderRead, setMessages]);
  const latestReadOwnerRef = useRef<ThreadTranscript | undefined>(undefined);
  const detailRequestsRef = useRef(new Map<string, {
    owner: ThreadTranscript;
    promise: Promise<{ ref: string; events: ThreadProjectionEvent[] } | null>;
  }>());

  useEffect(() => {
    if (!historyKey) return;
    const owner = transcriptRef.current;
    const controller = new AbortController();
    latestReadRef.current = controller;
    latestRefreshQueued.current = false;
    const generation = chatId ? client.getRunGeneration(chatId) : 0;
    const read = owner.begin(latestReadOwnerRef.current === owner ? "latest" : "initial");
    latestReadOwnerRef.current = owner;
    publishHistory();
    let disposed = false;
    let superseded = false;
    let publishing = false;
    const install = (body: Awaited<ReturnType<typeof fetchWebuiThread>>, ownRead: boolean, seed = false) => {
      if (disposed || (ownRead && superseded) || transcriptRef.current !== owner) return;
      flushPendingStreamEvents();
      const decision = ownRead ? read : owner.begin(seed ? "initial" : "latest");
      const canonical = body ? persistedCanonicalRunState(body) : null;
      const historyChatId = chatId ?? (historyKey.startsWith("websocket:") ? historyKey.slice(10) : null);
      if (historyChatId && canonical?.snapshot.activeTurnId
        && client.isRunCompleted(historyChatId, canonical.snapshot.activeTurnId)) {
        // An HTTP snapshot captured before a received terminal fact cannot
        // restore that turn's pending state or enter the shared replay cache.
        owner.observeTurnCompletion(canonical.snapshot.activeTurnId);
        owner.finishRead(decision);
        publishHistory();
        return;
      }
      const settle = chatId && canonical && !canonical.snapshot.hasPendingToolCalls
        && client.canReconcileCanonicalCompletion(chatId, generation, canonical.completedTurnIds, canonical.snapshot);
      const accepted = owner.accept(body, decision);
      // Commit the received owner before cache listeners/ledger callbacks can reenter.
      setMessages(owner.messages);
      if (accepted && chatId) messageCache?.set(chatId, owner.save());
      if (ownRead) {
        publishing = true;
        if (body) webuiThreadCache.set(historyKey, body);
        else webuiThreadCache.delete(historyKey);
        publishing = false;
      }
      if (ownRead && chatId && canonical) {
        if (accepted && settle && client.reconcileCanonicalCompletion(chatId, generation,
          canonical.completedTurnIds, canonical.snapshot)) {
          setRetryStatus(null);
        } else client.fenceCanonicalCompletedTurns(chatId, canonical.completedTurnIds);
      }
    };
    const cached = webuiThreadCache.get(historyKey);
    if (cached && owner.paging.version === 0) install(cached, false, true);
    const unsubscribe = webuiThreadCache.subscribe(historyKey, (body) => {
      if (publishing) return;
      superseded = true;
      controller.abort();
      cancelOlderRead();
      install(body, false);
    });
    void fetchLatestWebuiThread(client, getToken(), historyKey, controller.signal)
      .then((body) => install(body, true))
      .catch((error: unknown) => {
        if (disposed || superseded || controller.signal.aborted || transcriptRef.current !== owner) return;
        if (error instanceof ApiError && error.status === 404) install(null, true);
        else { owner.finishRead(read, (error as Error).message); publishHistory(); }
      }).finally(() => {
        if (latestReadRef.current !== controller) return;
        latestReadRef.current = undefined;
        if (latestRefreshQueued.current) {
          latestRefreshQueued.current = false;
          setRefreshSeq((value) => value + 1);
        }
      });
    return () => {
      disposed = true;
      controller.abort();
      cancelOlderRead();
      unsubscribe();
      if (latestReadRef.current === controller) {
        latestReadRef.current = undefined;
        latestRefreshQueued.current = false;
      }
    };
  }, [cancelOlderRead, chatId, client, flushPendingStreamEvents, getToken, historyKey, messageCache, publishHistory, refreshSeq, setMessages]);

  const loadOlder = useCallback(async () => {
    const owner = transcriptRef.current;
    const before = owner.paging.beforeCursor;
    if (!historyKey || !before || !owner.paging.hasMoreBefore || owner.paging.loadingOlder) return;
    const read = owner.begin("older");
    const controller = new AbortController();
    const operation = { owner, read, controller };
    olderReadRef.current = operation;
    publishHistory();
    try {
      const body = await fetchWebuiThread(getToken(), historyKey, { before, limit: 120, signal: controller.signal });
      if (olderReadRef.current !== operation || transcriptRef.current !== owner) return;
      flushPendingStreamEvents();
      owner.accept(body, read);
      setMessages(owner.messages);
    } catch (error) {
      if (olderReadRef.current === operation && transcriptRef.current === owner) {
        owner.finishRead(read, (error as Error).message);
        publishHistory();
      }
    } finally {
      if (olderReadRef.current === operation) olderReadRef.current = null;
    }
  }, [flushPendingStreamEvents, getToken, historyKey, publishHistory, setMessages]);

  const loadTraceDetails = useCallback(async (refs: string[]) => {
    const owner = transcriptRef.current;
    if (!historyKey) return [];
    const details = await Promise.all(refs.map((ref) => {
      const id = `${historyKey}:${ref}`;
      const existing = detailRequestsRef.current.get(id);
      if (existing?.owner === owner) return existing.promise;
      const request = fetchWebuiThreadTraceDetail(getToken(), historyKey, ref).then((detail) => {
        if (transcriptRef.current !== owner) return null;
        flushPendingStreamEvents();
        owner.expandDetail(ref, detail.events);
        setMessages(owner.messages);
        return { ref, events: detail.events };
      }).finally(() => {
        if (detailRequestsRef.current.get(id)?.promise === request) detailRequestsRef.current.delete(id);
      });
      detailRequestsRef.current.set(id, { owner, promise: request });
      return request;
    }));
    return details.filter((detail) => detail !== null);
  }, [flushPendingStreamEvents, getToken, historyKey, setMessages]);

  useEffect(() => {
    if (!chatId) return;

    const handle = (ev: InboundEvent) => {
      if (ev.event === "error") {
        if (ev.detail === "message_too_big") {
          applyStreamError({
            kind: "message_too_big",
            chatId,
            turnId: ev.turn_id,
          });
        } else if (ev.detail === "workspace_scope_rejected") {
          applyStreamError({
            kind: "workspace_scope_rejected",
            reason: ev.reason,
            chatId,
            turnId: ev.turn_id,
          });
        } else if (ev.turn_id) {
          applyStreamError({
            kind: "turn_rejected",
            detail: ev.detail,
            reason: ev.reason,
            chatId,
            turnId: ev.turn_id,
          });
        }
        return;
      }
      const turnId = eventTurnId(ev);
      if (turnId) {
        setMessages((prev) => transitionTurnDelivery(prev, turnId, "accepted"));
      }
      if (ev.event === "message_accepted") {
        if (ev.media_urls?.length) {
          setMessages((prev) => prev.map((message) => (
            message.role === "user" && message.turnId === ev.turn_id
              ? { ...message, media: ev.media_urls }
              : message
          )));
        }
        return;
      }
      if (ev.event === "user_message") {
        if (ev.provenance?.session_message) {
          flushPendingStreamEvents();
          closeActiveAssistantStream();
          clearActivitySegment();
          setMessages((prev) => {
            const next = appendProjectedSessionInput(prev, ev);
            if (next !== prev) transcriptRef.current.registerInput(next[next.length - 1]);
            return next;
          });
          return;
        }
        setMessages((prev) => {
          if (ev.turn_id && prev.some((message) => (
            message.role === "user" && message.turnId === ev.turn_id
          ))) return ev.media_urls?.length ? prev.map((message) => (
            message.role === "user" && message.turnId === ev.turn_id
              ? { ...message, media: ev.media_urls }
              : message
          )) : prev;
          const row: UIMessage = {
              id: crypto.randomUUID(),
              role: "user",
              content: ev.text,
              ...(ev.turn_id ? { turnId: ev.turn_id } : {}),
              turnPhase: "user",
              turnSeq: 0,
              deliveryStatus: "accepted",
              createdAt: typeof ev.created_at_ms === "number"
                && Number.isFinite(ev.created_at_ms)
                ? ev.created_at_ms
                : Date.now(),
              ...(ev.media_urls?.length ? { media: ev.media_urls } : {}),
              ...(ev.cli_apps?.length ? { cliApps: ev.cli_apps } : {}),
              ...(ev.mcp_presets?.length ? { mcpPresets: ev.mcp_presets } : {}),
              ...(ev.session_mentions?.length
                ? { sessionMentions: ev.session_mentions }
                : {}),
          };
          transcriptRef.current.registerInput(row);
          return [...prev, row];
        });
        return;
      }
      const sideChannelEvent = isSideChannelEvent(ev);
      if (!sideChannelEvent && (ev.event === "delta" || ev.event === "reasoning_delta"
        || ev.event === "file_edit" || ev.event === "message")
        && (!turnId || !client.isRunCompleted(chatId, turnId))) {
        setRecoveryState(null);
        setStreamError(null);
      }
      if (ev.event === "context_compaction") {
        flushPendingStreamEvents();
        closeActiveAssistantStream();
        clearActivitySegment();
        const previous = transcriptRef.current.messages.find((row) => row.id === `compaction-${ev.compaction_id}`);
        if (acceptsCompactionPhase(previous?.compaction?.phase, ev.phase)) applyProjectionEvent(ev);
        return;
      }
      if (
        ev.event === "delta"
        || ev.event === "message"
        || ev.event === "file_edit"
        || ev.event === "reasoning_delta"
        || ev.event === "stream_end"
      ) setRetryStatus(null);
      if (ev.event === "delta") {
        if (transcriptRef.current.projection.suppressUntilTurnEnd || transcriptRef.current.represented(ev)) return;
        const chunk = typeof ev.text === "string" ? ev.text : "";
        if (!chunk) return;
        enqueueStreamEvent({
          kind: "delta",
          text: chunk,
          turn: turnFieldsFromEvent(ev, "answer"),
          streamId: ev.stream_id,
          source: ev.source,
          responseSources: ev.response_sources,
        });
        return;
      }

      if (ev.event === "reasoning_delta") {
        if (transcriptRef.current.projection.suppressUntilTurnEnd || transcriptRef.current.represented(ev)) return;
        const chunk = ev.text;
        if (!chunk) return;
        enqueueStreamEvent({
          kind: "reasoning",
          text: chunk,
          turn: turnFieldsFromEvent(ev, "reasoning"),
          streamId: ev.stream_id,
        });
        return;
      }

      if (ev.event === "stream_end") {
        if (transcriptRef.current.represented(ev)) return;
        flushPendingStreamEvents(ev);
        if (transcriptRef.current.projection.suppressUntilTurnEnd) return;
        if (ev.resuming) {
          return;
        }
        // ``stream_end`` closes the current answer segment, not the turn.
        // Tools and follow-up model segments may still arrive before the
        // definitive ``turn_end`` event.
        return;
      }

      flushPendingStreamEvents();

      if (ev.event === "reasoning_end") {
        if (transcriptRef.current.projection.suppressUntilTurnEnd) return;
        applyProjectionEvent(ev);
        return;
      }

      if (ev.event === "goal_state") {
        setGoalState(ev.goal_state);
        return;
      }

      if (ev.event === "goal_status") {
        if (ev.status === "running") { setStreamError(null); setRecoveryState(null); }
        else setRetryStatus(null);
        return;
      }

      if (ev.event === "retry_status") {
        const activeTurnId = client.getRunTurnId(chatId);
        if (ev.turn_id && activeTurnId && ev.turn_id !== activeTurnId) return;
        if (ev.state === "recovered" || ev.state === "cleared") {
          setRetryStatus(null);
        } else {
          const retryAfterSeconds =
            typeof ev.retry_after_s === "number" &&
            Number.isFinite(ev.retry_after_s) &&
            ev.retry_after_s >= 0
              ? ev.retry_after_s
              : undefined;
          setRetryStatus({
            state: ev.state,
            attempt: ev.attempt,
            error_kind: ev.error_kind,
            ...(typeof ev.max_attempts === "number"
              ? { max_attempts: ev.max_attempts }
              : {}),
            ...(retryAfterSeconds !== undefined
              ? { next_retry_at: Date.now() / 1000 + retryAfterSeconds }
              : {}),
            ...(ev.turn_id ? { turn_id: ev.turn_id } : {}),
          });
        }
        return;
      }

      if (ev.event === "turn_end") {
        if (typeof ev.turn_id === "string") transcriptRef.current.sideChannelTurnIds.delete(ev.turn_id);
        if ("goal_state" in ev && ev.goal_state != null && typeof ev.goal_state === "object") {
          setGoalState(ev.goal_state);
        }
        setRetryStatus(null);
        const modelRequestFailed = ev.outcome === "failed" && ev.failure_kind === "model";
        const failureAttempts =
          typeof ev.failure_attempts === "number"
          && Number.isInteger(ev.failure_attempts)
          && ev.failure_attempts > 0
            ? ev.failure_attempts
            : undefined;
        const modelFailure = modelRequestFailed
          ? {
              kind: "model_request_failed" as const,
              chatId,
              ...(ev.turn_id ? { turnId: ev.turn_id } : {}),
              ...(typeof ev.failure_error_kind === "string"
                ? { errorKind: ev.failure_error_kind }
                : {}),
              ...(failureAttempts !== undefined ? { attempts: failureAttempts } : {}),
            }
          : null;
        if (modelFailure) setStreamError(modelFailure);
        applyProjectionEvent(ev);
        playTurnCompleteSound();
        onTurnEnd?.();
        return;
      }

      if (ev.event === "recovery_state") {
        const next: RecoveryState = {
          status: ev.status,
          recovery_id: ev.recovery_id,
          ...(ev.reason ? { reason: ev.reason } : {}),
          ...(typeof ev.attempts === "number" ? { attempts: ev.attempts } : {}),
          ...(typeof ev.can_continue === "boolean"
            ? { can_continue: ev.can_continue }
            : {}),
          ...(typeof ev.failure_error_kind === "string"
            ? { failure_error_kind: ev.failure_error_kind }
            : {}),
          ...(typeof ev.reply_preserved === "boolean"
            ? { reply_preserved: ev.reply_preserved }
            : {}),
        };
        setRecoveryState(next);
        if (ev.reason === "model_request_failed" || ev.status === "resuming") {
          setStreamError(null);
        }
        if (
          ev.status === "awaiting_user"
          || ev.status === "recovered"
          || ev.status === "failed"
        ) {
          setRetryStatus(null);
          clearPendingStreamWork();
          closeActiveAssistantStream();
          clearActivitySegment();
        }
        return;
      }

      if (ev.event === "attached") {
        setRecoveryState(ev.recovery_state ?? null);
        if (
          ev.recovery_state?.reason === "model_request_failed"
          || ev.recovery_state?.status === "resuming"
        ) {
          setStreamError(null);
        }
        if (
          ev.recovery_state?.status === "awaiting_user"
          || ev.recovery_state?.status === "failed"
        ) {
          clearPendingStreamWork();
          closeActiveAssistantStream();
          clearActivitySegment();
        }
        return;
      }

      if (ev.event === "message") {
        applyProjectionEvent(ev, { sideChannel: sideChannelEvent });
        if (sideChannelEvent && typeof ev.turn_id === "string") {
          transcriptRef.current.sideChannelTurnIds.delete(ev.turn_id);
        }
        return;
      }
      if (ev.event === "file_edit") {
        applyProjectionEvent(ev);
        return;
      }
    };

    const unsub = client.onTranscript(chatId, handle);
    return () => {
      unsub();
      // Navigation may happen before the throttled paint. Snapshot the pending
      // deltas synchronously while they still belong to this subscription.
      const snapshot = snapshotStreamEvents(messagesRef.current);
      onStreamDetach?.(snapshot);
      if (snapshot !== messagesRef.current) setMessages(snapshot);
      messageCache?.set(chatId, transcriptRef.current.save());
      clearPendingStreamWork();
    };
  }, [
    applyProjectionEvent,
    snapshotStreamEvents,
    applyStreamError,
    chatId,
    closeActiveAssistantStream,
    client,
    clearActivitySegment,
    clearPendingStreamWork,
    flushPendingStreamEvents,
    isSideChannelEvent,
    onTurnEnd,
    onStreamDetach,
    messageCache,
    enqueueStreamEvent,
    setMessages,
  ]);

  const send = useCallback(
    (content: string, images?: SendAttachment[], options?: SendOptions) => {
      if (!chatId) return null;
      const hasAttachments = !!images && images.length > 0;
      // Text is optional when files are attached — the agent will still see
      // them via ``media`` paths.
      if (!hasAttachments && !content.trim()) return null;

      setStreamError(null);
      const sideChannel = options?.sideChannel === true;
      const finalizeActiveTurn = options?.finalizeActiveTurn === true;
      const continueActiveTurn = options?.continueActiveTurn === true;
      const outboundContent = options?.quotedContext
        ? formatQuotedUserMessage(content, options.quotedContext)
        : content;
      flushPendingStreamEvents();
      if (finalizeActiveTurn) {
        client.finishRunLocally(chatId);
        setRetryStatus(null);
      }
      const turnId = crypto.randomUUID();
      const userMessageId = crypto.randomUUID();
      if (sideChannel) transcriptRef.current.sideChannelTurnIds.add(turnId);
      const previews = hasAttachments ? images!.map(({ preview }) => (
        preview.kind === "video" && preview.url?.startsWith("data:")
          ? { kind: preview.kind, name: preview.name }
          : preview
      )) : undefined;
      setMessages((prev) => {
        let projection = { ...transcriptRef.current.projection, messages: prev };
        if ((!sideChannel && !continueActiveTurn) || finalizeActiveTurn) {
          projection = resetThreadProjectionCursor(projection, prev);
        } else if (continueActiveTurn) {
          // Guidance belongs to the active backend turn. Preserve the answer
          // cursor so its resuming stream_end can finalize the text already
          // shown before the new user row, while starting fresh activity after it.
          projection = clearThreadProjectionActivity(projection);
        }
        const base = finalizeActiveTurn ? finalizeStreamedTurn(prev) : prev;
        const next: UIMessage[] = [
          ...base,
          {
            id: userMessageId,
            role: "user" as const,
            content: outboundContent,
            turnId,
            turnPhase: "user",
            turnSeq: 0,
            deliveryStatus: "sending" as const,
            createdAt: Date.now(),
            ...(previews ? { media: previews } : {}),
            ...(options?.cliApps?.length ? { cliApps: options.cliApps } : {}),
            ...(options?.mcpPresets?.length ? { mcpPresets: options.mcpPresets } : {}),
            ...(options?.sessionMentions?.length
              ? { sessionMentions: options.sessionMentions }
              : {}),
            },
        ];
        transcriptRef.current.projection = { ...projection, messages: next };
        transcriptRef.current.registerInput(next[next.length - 1]);
        return next;
      });
      const wireMedia = hasAttachments ? images!.map((i) => i.media) : undefined;
      const clientOptions = {
        ...options,
        turnId,
        ...((sideChannel || continueActiveTurn) ? { startsNewRun: false } : {}),
      };
      delete clientOptions.quotedContext;
      delete clientOptions.sideChannel;
      delete clientOptions.finalizeActiveTurn;
      delete clientOptions.continueActiveTurn;
      const delivery = options?.userShell
        ? client.sendUserShellCommand(chatId, outboundContent, clientOptions)
        : wireMedia?.length
          ? client.sendAttachments(chatId, outboundContent, wireMedia, clientOptions)
          : client.sendTextMessage(chatId, outboundContent, clientOptions);
      // Every caller may keep this promise to retain its draft until accepted.
      // Also observe it here for queued/landing sends without an active composer.
      void delivery?.catch(() => {});
      return { turnId, userMessageId, sideChannel, delivery };
    },
    [chatId, clearActivitySegment, client, flushPendingStreamEvents, setMessages],
  );

  const stop = useCallback(async () => {
    if (!chatId) return;
    const owner = transcriptRef.current;
    const turnId = client.getRunTurnId(chatId);
    try {
      await client.sendSystemCommand(chatId, "/stop", 30_000);
    } catch (error) {
      if (transcriptRef.current !== owner) return;
      setStreamError({
        kind: "turn_rejected", chatId, turnId: client.getRunTurnId(chatId) ?? "",
        detail: "stop_failed", reason: error instanceof Error ? error.message : String(error),
      });
      return;
    }
    if (client.getRunTurnId(chatId) !== turnId) return;
    client.finishRunLocally(chatId);
    if (transcriptRef.current !== owner) return;
    flushPendingStreamEvents();
    setRetryStatus(null);
    setMessages((prev) => {
      const settled = prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m));
      transcriptRef.current.projection = resetThreadProjectionCursor(transcriptRef.current.projection, settled);
      return settled;
    });
  }, [chatId, clearActivitySegment, client, flushPendingStreamEvents, setMessages]);

  const recoveryAction = useCallback(async (action: "continue" | "dismiss") => {
    if (!chatId || !recoveryState) return;
    const owner = transcriptRef.current;
    await client.requestMutation(`recovery.${action}`, {
      chat_id: chatId,
      recovery_id: recoveryState.recovery_id,
    });
    if (transcriptRef.current === owner) {
      setRecoveryState(current => current === recoveryState
        ? { ...current, status: action === "continue" ? "resuming" : "recovered" }
        : current);
    }
  }, [chatId, client, recoveryState]);

  const continueRecovery = useCallback(
    () => recoveryAction("continue"),
    [recoveryAction],
  );
  const dismissRecovery = useCallback(
    () => recoveryAction("dismiss"),
    [recoveryAction],
  );

  return {
    messages,
    messagesReady: messageScope.chatId === chatId && messageScope.historyKey === historyKey && messageScope.client === client,
    isStreaming,
    runStartedAt,
    retryStatus,
    goalState,
    recoveryState,
    continueRecovery,
    dismissRecovery,
    send,
    stop,
    history: historyState,
    refreshHistory,
    resetHistory,
    loadOlder,
    loadTraceDetails,
    streamError,
    dismissStreamError,
  };
}
