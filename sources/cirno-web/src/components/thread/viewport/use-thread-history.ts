import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject, type RefObject } from "react";
import type { PromptHistoryNavigation } from "@/hooks/usePromptHistory";
import type { UIMessage } from "@/lib/contracts/messages";
import { isModelInput } from "@/lib/thread-inputs";
import { HISTORY_HOLD_PX, ThreadHistorySpring, type HistoryRevealPhase } from "../thread-history-spring";
import type { ThreadMotionCoordinator } from "../thread-motion";
import type { ThreadViewportInput } from "./input";
import {
  THREAD_DISPLAY_UNIT_SELECTOR, historyPrefetchDistance, visibleHistoryUnit,
  setHistoryPresentation, type HistoryScrollAnchor
} from "./geometry";
import { INITIAL_HISTORY_WINDOW, HISTORY_WINDOW_INCREMENT, windowMessages } from "./window";

interface HistoryOptions {
  messages: UIMessage[];
  hasMessages: boolean;
  conversationReady: boolean;
  userMessageOffset: number;
  forkBoundaryMessageCount: number | null;
  hasMoreBefore: boolean;
  loadingOlder: boolean;
  olderError: string | null;
  navigation?: PromptHistoryNavigation;
  onLoadOlder?: () => void | Promise<void>;
  scrollRef: MutableRefObject<HTMLDivElement | null>;
  messageRegionRef: MutableRefObject<HTMLDivElement | null>;
  messageContentRef: RefObject<HTMLDivElement | null>;
  threadMotionRef: MutableRefObject<ThreadMotionCoordinator | null>;
  pendingConversationScrollRef: MutableRefObject<boolean>;
  inputControllerRef: MutableRefObject<ThreadViewportInput | null>;
  setAtBottom: (value: boolean) => void;
}

/** Own the local history window, pull presentation and preserved reading position. */
export function useThreadHistory({ messages, hasMessages, conversationReady, userMessageOffset,
  forkBoundaryMessageCount, hasMoreBefore, loadingOlder, olderError, navigation, onLoadOlder,
  scrollRef, messageRegionRef, messageContentRef, threadMotionRef, pendingConversationScrollRef,
  inputControllerRef, setAtBottom }: HistoryOptions) {
  const restoreScrollAfterPrependRef =
    useRef<{ height: number; top: number; } | null>(null);

  const historyScrollAnchorRef = useRef<HistoryScrollAnchor | null>(null);

  const previousLoadingOlderRef = useRef(loadingOlder);

  const [atHistoryTop, setAtHistoryTop] = useState(false);

  const [historyPhase, setHistoryPhase] = useState<HistoryRevealPhase>("hidden");

  const historyPhaseRef = useRef(historyPhase);

  const [historySlotKey, setHistorySlotKey] = useState<string | null>(null);

  const historySlotCompleted = previousLoadingOlderRef.current && !loadingOlder && !olderError && historySlotKey !== null;

  const retainedHistorySlotKey = historySlotCompleted ? null : historySlotKey;

  const [showHistoryExhausted, setShowHistoryExhausted] = useState(false);

  const historySlotRef = useRef<HTMLDivElement | null>(null);

  const historyDistanceRef = useRef(0);

  const historyStatusRef = useRef<HTMLDivElement | null>(null);

  const historySpringRef = useRef<ThreadHistorySpring | null>(null);

  if (historySpringRef.current === null) {
    historySpringRef.current = new ThreadHistorySpring({
      onPhaseChange: (phase) => {
        const previous = historyPhaseRef.current;
        historyPhaseRef.current = phase;
        setHistoryPhase(phase);
        if (phase === "hidden" && previous === "feedback") setShowHistoryExhausted(false);
      },
      onUpdate: (distance) => {
        historyDistanceRef.current = distance;
        setHistoryPresentation(messageRegionRef.current, historyStatusRef.current, historySlotRef.current, distance);
      },
    });
  }

  const setMessageRegion = useCallback((element: HTMLDivElement | null) => {
    // React can reuse this div for the empty state; release imperative styles with the ref.
    messageRegionRef.current?.style.removeProperty("transform");
    messageRegionRef.current = element;
    setHistoryPresentation(element, historyStatusRef.current, historySlotRef.current, historyDistanceRef.current);
  }, [messageRegionRef]);

  const setHistoryStatus = useCallback((element: HTMLDivElement | null) => {
    historyStatusRef.current = element;
    setHistoryPresentation(messageRegionRef.current, element, historySlotRef.current, historyDistanceRef.current);
  }, [messageRegionRef]);

  const setHistorySlot = useCallback((element: HTMLDivElement | null) => {
    historySlotRef.current = element;
    setHistoryPresentation(messageRegionRef.current, historyStatusRef.current, element, historyDistanceRef.current);
  }, [messageRegionRef]);

  const [visibleMessageCount, setVisibleMessageCount] =
    useState(INITIAL_HISTORY_WINDOW);

  const visibleMessages = useMemo(
    () => windowMessages(messages, visibleMessageCount),
    [messages, visibleMessageCount],
  );

  const hiddenMessageCount = messages.length - visibleMessages.length;

  const historyExhausted = !hasMoreBefore && hiddenMessageCount === 0;

  const hiddenUserMessageCount =
    userMessageOffset
    + (hiddenMessageCount > 0
      ? messages.slice(0, hiddenMessageCount).filter(isModelInput).length
      : 0);

  const visibleForkBoundaryMessageCount =
    forkBoundaryMessageCount !== null && forkBoundaryMessageCount > hiddenMessageCount
      ? forkBoundaryMessageCount - hiddenMessageCount
      : null;

  const captureHistoryScrollAnchor = useCallback(() => {
    const scroller = scrollRef.current;
    const content = messageContentRef.current;
    if (!scroller || !content) {
      historyScrollAnchorRef.current = null;
      return false;
    }
    const viewport = scroller.getBoundingClientRect();
    const element = visibleHistoryUnit(content, viewport);
    const key = element?.dataset.threadDisplayUnit;
    if (!element || !key) {
      historyScrollAnchorRef.current = null;
      return false;
    }
    historyScrollAnchorRef.current = {
      key,
      scrollTop: scroller.scrollTop,
      // Normalize out the reveal lease, even when reading above its inline slot.
      offsetTop: element.getBoundingClientRect().top - viewport.top
        - (historySlotRef.current ? HISTORY_HOLD_PX : 0),
    };
    return true;
  }, [scrollRef, messageContentRef]);

  const reconcileHistoryScrollAnchor = useCallback(() => {
    const scroller = scrollRef.current;
    const content = messageContentRef.current;
    const anchor = historyScrollAnchorRef.current;
    if (!scroller || !content || !anchor) return false;
    const element = Array.from(
      content.querySelectorAll<HTMLElement>("[data-thread-display-unit]"),
    ).find((candidate) => candidate.dataset.threadDisplayUnit === anchor.key);
    if (!element) {
      historyScrollAnchorRef.current = null;
      return false;
    }

    const nextOffset =
      element.getBoundingClientRect().top
      - scroller.getBoundingClientRect().top
      - (historySlotRef.current ? HISTORY_HOLD_PX : 0);
    const delta = nextOffset - anchor.offsetTop;
    if (Math.abs(delta) < 0.5) return true;
    const maxScrollTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
    const nextTop = Math.min(maxScrollTop, Math.max(0, scroller.scrollTop + delta));
    threadMotionRef.current?.jumpTo(nextTop);
    anchor.scrollTop = scroller.scrollTop;
    return true;
  }, [scrollRef, messageContentRef, threadMotionRef]);

  const resetHistoryHeader = useCallback(() => {
    setHistorySlotKey(null);
    historySpringRef.current?.reset();
  }, []);

  const holdHistoryHeader = useCallback(() => {
    // A request at a new boundary supersedes the old slot. Mid-page retry
    // keeps its original boundary, never a hit-tested answer or activity row.
    if (!historySlotRef.current || (scrollRef.current && scrollRef.current.scrollTop <= 1)) {
      const unit = messageContentRef.current?.querySelector<HTMLElement>(THREAD_DISPLAY_UNIT_SELECTOR);
      if (unit?.dataset.threadDisplayUnit) setHistorySlotKey(unit.dataset.threadDisplayUnit);
    }
    historySpringRef.current?.hold();
  }, [scrollRef, messageContentRef]);

  const loadEarlierMessages = useCallback(() => {
    if (loadingOlder || navigation?.loading) return;
    const el = scrollRef.current;
    if (el) {
      if (captureHistoryScrollAnchor()) {
        restoreScrollAfterPrependRef.current = null;
      } else {
        restoreScrollAfterPrependRef.current = {
          height: el.scrollHeight,
          top: el.scrollTop,
        };
      }
    }
    threadMotionRef.current?.takeUserControl();
    setAtBottom(false);
    if (hiddenMessageCount > 0) {
      setVisibleMessageCount((count) =>
        Math.min(messages.length, count + HISTORY_WINDOW_INCREMENT),
      );
      return;
    }
    if (hasMoreBefore && onLoadOlder) {
      holdHistoryHeader();
      setVisibleMessageCount((count) => count + HISTORY_WINDOW_INCREMENT);
      void onLoadOlder();
    }
  }, [
    captureHistoryScrollAnchor,
    hasMoreBefore,
    hiddenMessageCount,
    holdHistoryHeader,
    loadingOlder,
    messages.length,
    navigation?.loading,
    onLoadOlder, scrollRef, threadMotionRef, setAtBottom,
  ]);

  const maybeLoadEarlierFromScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || !hasMessages || pendingConversationScrollRef.current) return;
    if (!threadMotionRef.current?.isBrowsingHistory()) return;
    if (el.scrollTop > historyPrefetchDistance(el)) return;
    if (hiddenMessageCount <= 0 && (inputControllerRef.current?.inputType === "touch" || el.scrollTop > 1)) return;
    if (hiddenMessageCount <= 0 && (!hasMoreBefore || olderError)) return;
    loadEarlierMessages();
  }, [hasMessages, hasMoreBefore, hiddenMessageCount, loadEarlierMessages, olderError, scrollRef, threadMotionRef, pendingConversationScrollRef, inputControllerRef]);

  const completeOlderLoad = useCallback(() => {
    const wasLoading = previousLoadingOlderRef.current;
    previousLoadingOlderRef.current = loadingOlder;
    if (!wasLoading || loadingOlder || olderError || !historySlotKey) return;
    // The completed render already removed the slot. Rebase the saved anchor
    // by its live presentation travel before the single final-geometry read.
    const anchor = historyScrollAnchorRef.current;
    if (anchor) anchor.offsetTop += historyDistanceRef.current;
    setShowHistoryExhausted(historyExhausted);
    resetHistoryHeader();
  }, [loadingOlder, olderError, historySlotKey, historyExhausted, resetHistoryHeader]);

  const restorePrepend = useCallback(() => {
    const pending = restoreScrollAfterPrependRef.current;
    const el = scrollRef.current;
    restoreScrollAfterPrependRef.current = null;
    if (!el) return;
    if (reconcileHistoryScrollAnchor()) return;
    if (!pending) return;
    const delta = el.scrollHeight - pending.height;
    const nextTop = Math.min(
      Math.max(0, el.scrollHeight - el.clientHeight),
      Math.max(0, pending.top + delta),
    );
    threadMotionRef.current?.jumpTo(nextTop);
  }, [reconcileHistoryScrollAnchor, scrollRef, threadMotionRef]);

  const reconcileRetainedSlot = useCallback(() => {
    // Replaced history windows cannot retain a slot for an unmounted boundary.
    if (retainedHistorySlotKey && !historySlotRef.current) resetHistoryHeader();
  }, [retainedHistorySlotKey, resetHistoryHeader, visibleMessages]);

  const holdForLoad = useCallback(() => {
    // A request commits temporary space; successful completion reclaims it below.
    if (conversationReady && loadingOlder && scrollRef.current?.scrollTop === 0 && !historySlotRef.current) {
      holdHistoryHeader();
    }
  }, [conversationReady, loadingOlder, holdHistoryHeader, scrollRef]);

  const clearHistoryPosition = useCallback(() => {
    historyScrollAnchorRef.current = null;
    restoreScrollAfterPrependRef.current = null;
  }, []);
  const resetHistory = useCallback(() => {
    clearHistoryPosition();
    resetHistoryHeader();
    setShowHistoryExhausted(false);
    setVisibleMessageCount(INITIAL_HISTORY_WINDOW);
  }, [clearHistoryPosition, resetHistoryHeader]);
  const revealThrough = useCallback((index: number, total: number) => {
    setVisibleMessageCount((count) => Math.max(count, total - index));
  }, []);
  const showPromptWindow = useCallback((index: number, total: number) => {
    setVisibleMessageCount(Math.max(INITIAL_HISTORY_WINDOW, total - Math.max(0, index)));
  }, []);
  useEffect(() => () => historySpringRef.current?.reset(), []);

  return {
    visibleMessages, hiddenMessageCount, hiddenUserMessageCount, visibleForkBoundaryMessageCount,
    atHistoryTop, setAtHistoryTop, historyPhase, historySlotKey, historySlotCompleted, retainedHistorySlotKey,
    showHistoryExhausted, historyExhausted, historyScrollAnchorRef, historySpring: historySpringRef.current,
    setMessageRegion, setHistoryStatus, setHistorySlot, captureHistoryScrollAnchor, reconcileHistoryScrollAnchor,
    resetHistoryHeader, holdHistoryHeader, loadEarlierMessages, maybeLoadEarlierFromScroll,
    completeOlderLoad, restorePrepend, reconcileRetainedSlot, holdForLoad,
    clearHistoryPosition, resetHistory, revealThrough, showPromptWindow,
  };
}
