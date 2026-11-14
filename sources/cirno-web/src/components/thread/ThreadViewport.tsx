import { conversationRole } from "@/lib/conversation-role";
import { useViewportCamera, useViewportTurn, useViewportGeometry } from "./viewport/motion";
import { ThreadViewportSurface } from "./viewport/ThreadViewportSurface";
import { useThreadHistory } from "./viewport/use-thread-history";
import { useComposerViewport } from "./viewport/use-composer-viewport";
import { ThreadViewportInput } from "./viewport/input";
import { useViewportInput } from "./viewport/use-input";
import type { ThreadViewportHandle, ThreadViewportProps } from "./viewport/contracts";
import { PROMPT_TOP_INSET_PX } from "./viewport/geometry";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
} from "react";

import { useHasSubagentResults } from "@/components/thread/SubagentTaskResults";
import { ThreadHistoryStatus } from "@/components/thread/ThreadHistoryStatus";
import {
  findPromptElement,
} from "@/components/thread/promptNavigation";
import { cn } from "@/lib/utils";

const DEFAULT_SCROLL_BUTTON_BOTTOM_PX = 192;
const EXTERNAL_COMPOSER_SCROLL_BUTTON_BOTTOM_PX = 16;
const SCROLL_BUTTON_COMPOSER_GAP_PX = 16;
const SESSION_HANDOFF_EXIT_DURATION_MS = 80;
const SESSION_HANDOFF_ENTER_DURATION_MS = 140;
const SESSION_HANDOFF_OPACITY = 0.82;

export const ThreadViewport = forwardRef<ThreadViewportHandle, ThreadViewportProps>(function ThreadViewport({
  messages: latestMessages,
  navigation,
  temporary = false,
  isStreaming: liveStreaming,
  runStartedAt = null,
  retryStatus = null,
  composer,
  navigationFrame,
  emptyState,
  initialLoading = false,
  scrollToBottomSignal = 0,
  activeTurnId: liveTurnId = null,
  activeTurnStartedHere = false,
  conversationKey = null,
  conversationReady = true,
  showScrollToBottomButton = true,
  cliApps = [],
  mcpPresets = [],
  slashCommands = [],
  forkBoundaryMessageCount: latestForkBoundary = null,
  hasMoreBefore: latestHasMoreBefore = false,
  loadingOlder: latestLoadingOlder = false,
  olderError: latestOlderError = null,
  userMessageOffset: latestUserOffset = 0,
  onLoadOlder: loadLatestOlder,
  traceDetailScope = null,
  onLoadTraceDetails,
  onOpenFilePreview,
  onForkFromMessage,
  onEditMessage,
  messageEditor,
  onQuoteSelection,
}, ref) {
  const historyWindow = navigation?.window;
  const messages = historyWindow?.messages ?? latestMessages;
  const isStreaming = !historyWindow && liveStreaming;
  const activeTurnId = historyWindow ? null : liveTurnId;
  const forkBoundaryMessageCount = historyWindow ? historyWindow.forkBoundaryMessageCount : latestForkBoundary;
  const hasMoreBefore = historyWindow?.hasMoreBefore ?? latestHasMoreBefore;
  const loadingOlder = historyWindow ? navigation!.operation === "older" && navigation!.loading : latestLoadingOlder;
  const olderError = historyWindow ? navigation!.operation === "older" ? navigation!.error : null : latestOlderError;
  const userMessageOffset = historyWindow?.userMessageOffset ?? latestUserOffset;
  const onLoadOlder = historyWindow ? navigation!.older : loadLatestOlder;
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const viewportFrameRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const messageRegionRef = useRef<HTMLDivElement | null>(null);
  const messageContentRef = useRef<HTMLDivElement>(null);
  const emptyStateRef = useRef<HTMLDivElement>(null);
  const composerDockRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastConversationKeyRef = useRef<string | null>(conversationKey);
  const conversationHandoffPendingRef = useRef(false);
  const conversationHandoffAnimationRef = useRef<Animation | null>(null);
  const pendingConversationScrollRef = useRef(true);
  const pendingPromptJumpRef = useRef<string | null>(null);
  const inputControllerRef = useRef<ThreadViewportInput | null>(null);
  const { threadMotionRef, motion, atBottom, setAtBottom, composerDockHeight, hasVerticalOverflow } = useViewportCamera(scrollRef, composerDockRef);
  const hasTaskResults = useHasSubagentResults();
  const hasMessages = messages.length > 0 || (hasTaskResults && conversationReady);
  const hasThreadLayout = hasMessages || initialLoading;
  useLayoutEffect(() => {
    scrollRef.current = hasMessages
      ? messageRegionRef.current
      : viewportFrameRef.current;
  }, [hasMessages]);
  const { visibleMessages, hiddenMessageCount, hiddenUserMessageCount, visibleForkBoundaryMessageCount,
    atHistoryTop, setAtHistoryTop, historyPhase, historySlotKey, historySlotCompleted, retainedHistorySlotKey,
    showHistoryExhausted, historyExhausted, historyScrollAnchorRef, historySpring,
    setMessageRegion, setHistoryStatus, setHistorySlot, captureHistoryScrollAnchor, reconcileHistoryScrollAnchor,
    resetHistoryHeader, loadEarlierMessages, maybeLoadEarlierFromScroll,
    completeOlderLoad, restorePrepend, reconcileRetainedSlot, holdForLoad,
    clearHistoryPosition, resetHistory, revealThrough, showPromptWindow,
  } = useThreadHistory({
    messages, hasMessages, conversationReady, userMessageOffset, forkBoundaryMessageCount,
    hasMoreBefore, loadingOlder, olderError, navigation, onLoadOlder,
    scrollRef, messageRegionRef, messageContentRef, threadMotionRef, pendingConversationScrollRef,
    inputControllerRef, setAtBottom,
  });
  useLayoutEffect(reconcileRetainedSlot, [reconcileRetainedSlot]);
  const hasComposer = composer !== null && composer !== undefined;

  const yieldCameraToUser = useCallback(() => {
    threadMotionRef.current?.takeUserControl();
  }, []);

  const scrollToBottomNow = useCallback((smooth = false) => {
    clearHistoryPosition();
    resetHistoryHeader();
    const el = scrollRef.current;
    const marker = bottomRef.current;
    const behavior: ScrollBehavior = smooth ? "smooth" : "auto";
    if (el) {
      const top = Math.max(0, el.scrollHeight - el.clientHeight);
      if (smooth) {
        threadMotionRef.current?.navigateLatestTo(top);
      } else {
        threadMotionRef.current?.jumpTo(top);
      }
    } else if (marker) {
      marker.scrollIntoView({ block: "end", behavior });
    }
    setAtBottom(true);
  }, [resetHistoryHeader]);

  const scrollToBottom = useCallback(
    (smooth = false, options?: { force?: boolean; }) => {
      const force = options?.force ?? false;
      if (!force && threadMotionRef.current?.isAutoFollowPaused()) return;
      if (!smooth) threadMotionRef.current?.resumeAutoFollow();
      scrollToBottomNow(smooth);
    },
    [scrollToBottomNow],
  );

  const navigateToVisiblePrompt = useCallback((promptId: string) => {
    const scrollEl = scrollRef.current;
    const prompt = scrollEl ? findPromptElement(scrollEl, promptId) : null;
    if (!scrollEl || !prompt) return false;
    historyScrollAnchorRef.current = null;
    resetHistoryHeader();
    setAtBottom(false);
    threadMotionRef.current?.navigateHistoryToPrompt(promptId);
    return true;
  }, [resetHistoryHeader]);

  const jumpToUserPrompt = useCallback((promptId: string) => {
    // A local destination also supersedes an in-flight remote jump.
    navigation?.cancel();
    pendingPromptJumpRef.current = null;
    if (navigateToVisiblePrompt(promptId)) return;
    if (navigation?.prompts.some((prompt) => prompt.id === promptId && prompt.cursor)) {
      threadMotionRef.current?.takeUserControl();
      navigation.jump(promptId);
      return;
    }
    const localMessages = historyWindow ? latestMessages : messages;
    const index = localMessages.findIndex((message) => message.id === promptId);
    if (index < 0) return;
    if (historyWindow) navigation?.latest();
    threadMotionRef.current?.takeUserControl();
    pendingPromptJumpRef.current = promptId;
    setAtBottom(false);
    revealThrough(index, localMessages.length);
  }, [historyWindow, latestMessages, messages, navigateToVisiblePrompt, navigation]);

  useLayoutEffect(() => {
    if (!navigation?.target) return;
    clearHistoryPosition();
    pendingConversationScrollRef.current = false;
    pendingPromptJumpRef.current = navigation.target.id;
    threadMotionRef.current?.takeUserControl();
    setAtBottom(false);
    const index = messages.findIndex((message) => message.id === navigation.target!.id);
    showPromptWindow(index, messages.length);
  }, [navigation?.target]);

  useEffect(() => {
    if (activeTurnStartedHere && liveTurnId) navigation?.latest();
  }, [activeTurnStartedHere, liveTurnId, navigation?.latest]);

  const cancelAutoScroll = useCallback(() => {
    threadMotionRef.current?.takeUserControl();
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      jumpToUserPrompt,
      cancelAutoScroll,
    }),
    [cancelAutoScroll, jumpToUserPrompt],
  );

  const keyboardInsetBottom = useComposerViewport(composerDockRef, hasMessages, scrollToBottom);
  const scrollButtonBottom =
    keyboardInsetBottom
    + (composerDockHeight > 0
      ? composerDockHeight + SCROLL_BUTTON_COMPOSER_GAP_PX
      : hasComposer
        ? DEFAULT_SCROLL_BUTTON_BOTTOM_PX
        : EXTERNAL_COMPOSER_SCROLL_BUTTON_BOTTOM_PX);
  const scrollViewportStyle =
    keyboardInsetBottom > 0 ? { bottom: keyboardInsetBottom } : undefined;

  useEffect(() => {
    if (scrollToBottomSignal <= 0) return;
    scrollToBottom(false, { force: true });
  }, [scrollToBottomSignal, scrollToBottom]);

  useLayoutEffect(() => {
    if (lastConversationKeyRef.current === conversationKey) return;
    lastConversationKeyRef.current = conversationKey;
    inputControllerRef.current?.reset();
    resetHistoryHeader();
    conversationHandoffAnimationRef.current?.cancel();
    conversationHandoffAnimationRef.current = null;
    conversationHandoffPendingRef.current = true;
    pendingConversationScrollRef.current = true;
    historyScrollAnchorRef.current = null;
    clearHistoryPosition();
    threadMotionRef.current?.reset();
    setAtBottom(true);
    resetHistory();

    const surface = hasMessages ? messageRegionRef.current : emptyStateRef.current;
    const reduceMotion = typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!surface || reduceMotion || typeof surface.animate !== "function") return;
    conversationHandoffAnimationRef.current = surface.animate(
      [{ opacity: 1 }, { opacity: SESSION_HANDOFF_OPACITY }],
      {
        duration: SESSION_HANDOFF_EXIT_DURATION_MS,
        easing: "cubic-bezier(0.2, 0, 0, 1)",
        fill: "forwards",
      },
    );
  }, [conversationKey, hasMessages, resetHistoryHeader]);
  useViewportTurn({ threadMotionRef, conversationReady, activeTurnId, activeTurnStartedHere, messages, pendingConversationScrollRef });
  useLayoutEffect(completeOlderLoad, [completeOlderLoad]);
  useLayoutEffect(restorePrepend, [restorePrepend, visibleMessages.length, messages, loadingOlder]);

  useLayoutEffect(() => {
    const promptId = pendingPromptJumpRef.current;
    const scrollEl = scrollRef.current;
    if (!promptId || !scrollEl || !findPromptElement(scrollEl, promptId)) return;
    const frame = window.requestAnimationFrame(() => {
      if (pendingPromptJumpRef.current === promptId && navigateToVisiblePrompt(promptId)) {
        pendingPromptJumpRef.current = null;
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [navigateToVisiblePrompt, visibleMessages, navigation?.target]);

  useLayoutEffect(() => {
    if (!pendingConversationScrollRef.current) return;
    if (!conversationReady) return;
    if (!conversationKey) {
      pendingConversationScrollRef.current = false;
      scrollToBottom(false, { force: true });
      return;
    }
    scrollToBottom(false, { force: true });
    if (!hasMessages) return;
    pendingConversationScrollRef.current = false;
  }, [
    conversationKey,
    conversationReady,
    hasMessages,
    messages,
    scrollToBottom,
  ]);
  useLayoutEffect(holdForLoad, [holdForLoad]);

  useLayoutEffect(() => {
    if (!conversationReady || !conversationHandoffPendingRef.current) return;
    conversationHandoffPendingRef.current = false;
    conversationHandoffAnimationRef.current?.cancel();
    conversationHandoffAnimationRef.current = null;
    const surface = hasMessages ? messageRegionRef.current : emptyStateRef.current;
    const reduceMotion = typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!surface || reduceMotion || typeof surface.animate !== "function") return;

    const animation = surface.animate(
      [{ opacity: SESSION_HANDOFF_OPACITY }, { opacity: 1 }],
      {
        duration: SESSION_HANDOFF_ENTER_DURATION_MS,
        easing: "cubic-bezier(0.2, 0, 0, 1)",
      },
    );
    conversationHandoffAnimationRef.current = animation;
    const clearAnimation = () => {
      if (conversationHandoffAnimationRef.current === animation) {
        conversationHandoffAnimationRef.current = null;
      }
    };
    animation.onfinish = clearAnimation;
    animation.oncancel = clearAnimation;
  }, [conversationReady, hasMessages]);

  useLayoutEffect(() => {
    threadMotionRef.current?.invalidateGeometry();
  }, [composer, hasMessages, visibleMessages.length]);

  useEffect(() => () => {
    conversationHandoffAnimationRef.current?.cancel();
  }, []);
  useViewportGeometry({ scrollRef, contentRef, messageRegionRef, messageContentRef, composerDockRef, threadMotionRef, hasMessages, reconcileHistoryScrollAnchor });

  useViewportInput(inputControllerRef, scrollRef, {
    motion,
    spring: historySpring,
    anchor: historyScrollAnchorRef,
    pendingInitialScroll: pendingConversationScrollRef,
    messageContent: messageContentRef,
    messagesLength: messages.length,
    conversationReady, loadingOlder, hiddenMessageCount, hasMoreBefore,
    olderError, historySlotKey, historyWindow, navigation,
    setAtBottom, setAtHistoryTop, captureHistoryScrollAnchor,
    maybeLoadEarlierFromScroll, loadEarlierMessages, yieldCameraToUser, resetHistoryHeader,
  });

  const navigationStatus = navigation?.operation !== "older" && Boolean(navigation?.loading || navigation?.error);
  const showHistoryStatus = !historySlotCompleted && !navigationStatus && messages.length > 0 && conversationReady
    && (atHistoryTop && (!historyExhausted || showHistoryExhausted) || historyPhase !== "hidden" || loadingOlder);
  const historyStatus = showHistoryStatus ? (
    <ThreadHistoryStatus
      ref={setHistoryStatus}
      loading={loadingOlder}
      error={olderError}
      exhausted={historyExhausted}
      preview={historyPhase === "feedback"}
      onRetry={loadEarlierMessages}
      className={!retainedHistorySlotKey && !(historyExhausted && showHistoryExhausted) ? cn("thread-history-reveal", historyPhase === "feedback" && "thread-history-feedback") : undefined}
    />
  ) : null;

  return <ThreadViewportSurface
    nodes={{ viewportFrameRef, contentRef, messageContentRef, emptyStateRef, composerDockRef, bottomRef, scrollRef }}
    setMessageRegion={setMessageRegion} setHistorySlot={setHistorySlot}
    hasMessages={hasMessages} hasThreadLayout={hasThreadLayout} hasComposer={hasComposer}
    hasVerticalOverflow={hasVerticalOverflow} scrollViewportStyle={scrollViewportStyle}
    composer={composer} emptyState={emptyState} initialLoading={initialLoading} conversationKey={conversationKey}
    messageProps={{
      defaultActivityCollapsed: conversationRole(conversationKey).toolReplies,
      assistantBubbles: conversationRole(conversationKey).toolReplies,
      activityGrouping: conversationRole(conversationKey).toolReplies ? "conversation" : "turn",
      messages: visibleMessages,
      topInset: PROMPT_TOP_INSET_PX,
      temporary: temporary,
      isStreaming: isStreaming,
      activeTurnId: activeTurnId,
      runStartedAt: runStartedAt,
      retryStatus: retryStatus,
      hiddenUserMessageCount: hiddenUserMessageCount,
      cliApps: cliApps,
      mcpPresets: mcpPresets,
      slashCommands: slashCommands,
      forkBoundaryMessageCount: visibleForkBoundaryMessageCount,
      traceDetailScope: traceDetailScope,
      onLoadTraceDetails: onLoadTraceDetails,
      onOpenFilePreview: onOpenFilePreview,
      onForkFromMessage: onForkFromMessage,
      onEditMessage: onEditMessage,
      messageEditor: messageEditor,
      onQuoteSelection: onQuoteSelection,
      onActivityToggle: yieldCameraToUser
    }}
    retainedHistorySlotKey={retainedHistorySlotKey} historyStatus={historyStatus}
    navigationStatus={navigationStatus && navigation ? <ThreadHistoryStatus loading={navigation.loading}
      error={navigation.error} onRetry={navigation.retry} /> : null}
    messages={messages} navigation={navigation} navigationFrame={navigationFrame}
    onJumpToPrompt={jumpToUserPrompt} showLatestButton={showScrollToBottomButton && (!atBottom || Boolean(historyWindow))}
    scrollButtonBottom={scrollButtonBottom} onComposerInput={() => threadMotionRef.current?.handleComposerInput()}
    onScrollLatest={() => {
      navigation?.latest();
      if (historyWindow) { pendingConversationScrollRef.current = true; resetHistory(); }
      else scrollToBottom(true, { force: true });
    }}
  />;
});
