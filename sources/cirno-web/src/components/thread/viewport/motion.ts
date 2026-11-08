import { useEffect, useLayoutEffect, useRef, useState, type MutableRefObject, type RefObject } from "react";
import type { UIMessage } from "@/lib/contracts/messages";
import { ThreadCameraController } from "../thread-camera";
import { ThreadMotionCoordinator, type ThreadMotionGeometry } from "../thread-motion";
import { findPromptElement, promptTop } from "../promptNavigation";
import { promptTopInset } from "./geometry";

type MotionRef = MutableRefObject<ThreadMotionCoordinator | null>;

export function useViewportCamera(scrollRef: RefObject<HTMLDivElement | null>, composerDockRef: RefObject<HTMLDivElement | null>) {
  const composerDockHeightRef = useRef(0);
  const [atBottom, setAtBottom] = useState(true);
  const [composerDockHeight, setComposerDockHeight] = useState(0);
  const [hasVerticalOverflow, setHasVerticalOverflow] = useState(false);
  const threadMotionRef = useRef<ThreadMotionCoordinator | null>(null);
  if (threadMotionRef.current === null) {
    const camera = new ThreadCameraController(() => scrollRef.current);
    threadMotionRef.current = new ThreadMotionCoordinator({
      camera,
      measure: (promptId) => {
        const scrollEl = scrollRef.current;
        const composerDock = composerDockRef.current;
        if (!scrollEl) return null;
        const composerHeight = composerDock
          ? composerDock.getBoundingClientRect().height || composerDock.offsetHeight
          : 0;
        const prompt = promptId ? findPromptElement(scrollEl, promptId) : null;
        const scrollHeight = scrollEl.scrollHeight;
        const clientHeight = scrollEl.clientHeight;
        const maxScrollTop = Math.max(0, scrollHeight - clientHeight);
        return {
          scrollTop: scrollEl.scrollTop,
          scrollHeight,
          clientHeight,
          maxScrollTop,
          composerHeight,
          promptTop: prompt
            ? Math.min(
              maxScrollTop,
              Math.max(0, promptTop(scrollEl, prompt) - promptTopInset(scrollEl)),
            )
            : null,
        };
      },
      onGeometry: (geometry: ThreadMotionGeometry) => {
        if (Math.abs(composerDockHeightRef.current - geometry.composerHeight) >= 1) {
          composerDockHeightRef.current = geometry.composerHeight;
          setComposerDockHeight(geometry.composerHeight);
        }
        const nextOverflow = geometry.scrollHeight > geometry.clientHeight + 1;
        setHasVerticalOverflow((current) =>
          current === nextOverflow ? current : nextOverflow,
        );
      },
      onAutoFollow: () => setAtBottom(true),
    });
  }
  useEffect(() => () => threadMotionRef.current?.dispose(), []);
  return { threadMotionRef, motion: threadMotionRef.current, atBottom, setAtBottom, composerDockHeight, hasVerticalOverflow };
}

interface TurnOptions {
  threadMotionRef: MotionRef;
  conversationReady: boolean;
  activeTurnId: string | null;
  activeTurnStartedHere: boolean;
  messages: UIMessage[];
  pendingConversationScrollRef: MutableRefObject<boolean>;
}
export function useViewportTurn({ threadMotionRef, conversationReady, activeTurnId,
  activeTurnStartedHere, messages, pendingConversationScrollRef }: TurnOptions): void {
  useLayoutEffect(() => {
    if (!conversationReady) {
      threadMotionRef.current?.reset();
      return;
    }
    if (!activeTurnId) {
      threadMotionRef.current?.completeTurn();
      return;
    }

    const promptIndex = messages.findIndex(
      (message) => message.role === "user" && message.turnId === activeTurnId,
    );
    if (
      activeTurnStartedHere
      && promptIndex >= 0
      && threadMotionRef.current?.snapshot().turnId !== activeTurnId
    ) {
      // A turn submitted in this mounted viewport establishes a new prompt
      // origin. A restored turn must first complete open-at-bottom instead.
      pendingConversationScrollRef.current = false;
    }
    const prompt = promptIndex >= 0 ? messages[promptIndex] : null;
    const hasOutput = promptIndex >= 0
      ? messages
        .slice(promptIndex + 1)
        .some(
          (message) =>
            message.role !== "user"
            && (!message.turnId || message.turnId === activeTurnId),
        )
      : !activeTurnStartedHere && messages.some(
        (message) =>
          message.role !== "user" && message.turnId === activeTurnId,
      );
    threadMotionRef.current?.updateTurn({
      id: activeTurnId,
      promptId: prompt?.id ?? null,
      hasOutput,
      entry: activeTurnStartedHere ? "submitted" : "restored",
    });
  }, [activeTurnId, activeTurnStartedHere, conversationReady, messages, threadMotionRef, pendingConversationScrollRef]);
}

interface GeometryOptions {
  scrollRef: RefObject<HTMLDivElement | null>;
  contentRef: RefObject<HTMLDivElement | null>;
  messageRegionRef: RefObject<HTMLDivElement | null>;
  messageContentRef: RefObject<HTMLDivElement | null>;
  composerDockRef: RefObject<HTMLDivElement | null>;
  threadMotionRef: MotionRef;
  hasMessages: boolean;
  reconcileHistoryScrollAnchor: () => boolean;
}
export function useViewportGeometry({ scrollRef, contentRef, messageRegionRef, messageContentRef,
  composerDockRef, threadMotionRef, hasMessages, reconcileHistoryScrollAnchor }: GeometryOptions): void {
  useLayoutEffect(() => {
    const el = scrollRef.current;
    const content = contentRef.current;
    const messageRegion = messageRegionRef.current;
    const messageContent = messageContentRef.current;
    const composerDock = composerDockRef.current;
    if (!el) return;

    const invalidateGeometry = () => {
      threadMotionRef.current?.invalidateGeometry();
    };
    const reconcileObservedGeometry = () => {
      reconcileHistoryScrollAnchor();
      threadMotionRef.current?.reconcileObservedGeometry();
    };
    reconcileObservedGeometry();
    const observer = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(reconcileObservedGeometry);
    observer?.observe(el);
    if (content) observer?.observe(content);
    if (messageRegion) observer?.observe(messageRegion);
    if (messageContent) observer?.observe(messageContent);
    if (composerDock) observer?.observe(composerDock);
    window.addEventListener("resize", invalidateGeometry);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", invalidateGeometry);
    };
  }, [hasMessages, reconcileHistoryScrollAnchor, scrollRef, contentRef, messageRegionRef, messageContentRef, composerDockRef, threadMotionRef]);
}
