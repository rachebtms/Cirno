import type { ThreadViewportInputOptions } from "./input-contracts";
import { HISTORY_PREFETCH_MIN_PX, NEAR_BOTTOM_PX, THREAD_DISPLAY_UNIT_SELECTOR } from "./geometry";
import {
  isKeyboardEditableElement, isThreadDisclosureTarget, isKeyboardControl, directionFromDelta,
  keyboardScrollDirection, canScrollInDirection, type ThreadScrollDirection
} from "./input-geometry";

type HistoryTouch = {
  target: Node; lastY: number; startX: number; startY: number;
  pulling: boolean; horizontal: boolean
 };

/** Keep native listeners stable while committed history and turn state changes. */
export class ThreadViewportInput {
  inputType: "touch" | "other" = "other";
  private touch: HistoryTouch | null = null;
  private touchCleanup: (() => void) | null = null;
  private detach: (() => void) | null = null;
  private scroller: HTMLElement | null = null;

  constructor(private options: ThreadViewportInputOptions) { }

  update(options: ThreadViewportInputOptions): void { this.options = options; }

  private clearTouchTarget(): void {
    this.touchCleanup?.();
    this.touchCleanup = null;
  }

  reset(): void {
    this.clearTouchTarget();
    this.touch = null;
    this.inputType = "other";
  }

  disconnect(): void {
    this.detach?.();
    this.detach = null;
    this.scroller = null;
    this.reset();
  }

  connect(el: HTMLElement | null): void {
    if (el === this.scroller) return;
    this.disconnect();
    this.scroller = el;
    if (!el) return;
    const onScroll = (allowHistoryLoad = true) => {
      this.options.setAtHistoryTop(el.scrollTop <= 1);
      if (el.scrollTop > 1) this.options.spring.leaveBoundary();
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      const near = distance < NEAR_BOTTOM_PX;
      // A detached history page's bottom is not the live tail.
      const owner = this.options.motion.observeScroll(near && !this.options.historyWindow) ?? "automatic";
      const logicallyAtBottom = !this.options.historyWindow && (owner === "automatic" || (owner === "navigation" && near));
      this.options.setAtBottom(logicallyAtBottom);
      if (owner === "user") {
        // Restoring the anchor also emits scroll. Keep that reading position
        // through lazy content resizing instead of selecting a prepended row.
        const anchor = this.options.anchor.current;
        if (!anchor || el.scrollTop !== anchor.scrollTop) this.options.captureHistoryScrollAnchor();
        if (allowHistoryLoad) this.options.maybeLoadEarlierFromScroll();
        if (allowHistoryLoad && distance < HISTORY_PREFETCH_MIN_PX
          && this.options.historyWindow?.hasMoreAfter && !this.options.navigation?.loading && !this.options.navigation?.error) this.options.navigation?.newer();
      } else if (near) {
        this.options.anchor.current = null;
      }
    };

    onScroll(false);
    const handleScroll = () => onScroll(true);
    const atHistoryBoundary = () => el.scrollTop <= 1 && this.options.messagesLength > 0 && this.options.conversationReady
      && !this.options.pendingInitialScroll.current;
    const canLoadAtTop = () => atHistoryBoundary() && !this.options.loadingOlder && !this.options.navigation?.loading
      && (this.options.hiddenMessageCount > 0 || this.options.hasMoreBefore);
    const handleDirectionalInput = (
      direction: ThreadScrollDirection | null,
    ) => {
      if (!direction) return;
      if (direction === "forward" && this.options.historyWindow?.hasMoreAfter
        && el.scrollHeight - el.scrollTop - el.clientHeight < HISTORY_PREFETCH_MIN_PX
        && !this.options.navigation?.loading) {
        this.options.captureHistoryScrollAnchor();
        this.options.navigation?.newer();
      }
      // At the top (including a page too short to scroll), backward intent
      // produces no scroll event. It must still be able to reveal history.
      if (direction === "backward" && canLoadAtTop()) {
        this.options.loadEarlierMessages();
        return;
      }
      this.options.motion.handleUserScrollIntent(
        canScrollInDirection(el, direction),
        direction === "forward" && !this.options.historyWindow,
      );
    };
    const prepareHistoryPull = () => {
      if (this.options.loadingOlder || this.options.navigation?.loading) return;
      const first = this.options.messageContent.current?.querySelector<HTMLElement>(THREAD_DISPLAY_UNIT_SELECTOR);
      // A retained header belongs to the page boundary where it was opened,
      // not to a newer boundary reached by scrolling through prepended history.
      if (this.options.historySlotKey && first?.dataset.threadDisplayUnit !== this.options.historySlotKey) this.options.resetHistoryHeader();
    };
    const handleWheel = (event: WheelEvent) => {
      if (
        event.defaultPrevented
        || event.ctrlKey
        || Math.abs(event.deltaY) <= Math.abs(event.deltaX)
      ) {
        return;
      }
      this.inputType = "other";
      if (atHistoryBoundary()) {
        const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? 16
          : event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? el.clientHeight : 1;
        if (event.deltaY < 0) {
          prepareHistoryPull();
          this.options.yieldCameraToUser();
          this.options.setAtHistoryTop(true);
          const first = this.options.spring.wheel(-event.deltaY * unit);
          if ((first || this.options.olderError) && canLoadAtTop()) this.options.loadEarlierMessages();
          return;
        }
      }
      handleDirectionalInput(directionFromDelta(event.deltaY));
    };
    const handlePointerDown = (event: PointerEvent) => {
      if (
        event.button === 0
        && (event.target === el || isThreadDisclosureTarget(event.target))
      ) {
        this.options.yieldCameraToUser();
      }
    };
    const handleTouchCancel = () => {
      this.clearTouchTarget();
      this.touch = null;
      this.options.spring.endTouch(true);
    };
    const handleTouchStart = (event: TouchEvent) => {
      this.inputType = "touch";
      const touch = event.touches[0];
      if (event.touches.length !== 1 || !touch) {
        handleTouchCancel();
        return;
      }
      this.clearTouchTarget();
      const target = event.target as Node;
      this.touch = {
        target,
        lastY: touch.clientY,
        startX: touch.clientX,
        startY: touch.clientY,
        pulling: false,
        horizontal: false,
      };
      observeHistoryTouchTarget(target);
    };
    const handleTouchMove = (event: TouchEvent) => {
      const gesture = this.touch;
      const touch = event.touches[0];
      if (event.touches.length !== 1) {
        handleTouchCancel();
        return;
      }
      if (!gesture || !touch || event.defaultPrevented) return;
      const delta = gesture.lastY - touch.clientY;
      gesture.lastY = touch.clientY;
      const horizontalTravel = Math.abs(touch.clientX - gesture.startX);
      const verticalTravel = Math.abs(touch.clientY - gesture.startY);
      if (!gesture.pulling && horizontalTravel > verticalTravel) gesture.horizontal = true;
      if (gesture.horizontal) return;
      if (gesture.pulling || (atHistoryBoundary() && delta < 0 && this.options.hiddenMessageCount === 0)) {
        if (!gesture.pulling) {
          prepareHistoryPull();
          this.options.spring.startTouch();
          gesture.pulling = true;
        }
        if (event.cancelable) event.preventDefault();
        this.options.yieldCameraToUser();
        this.options.spring.moveTouch(-delta);
        this.options.setAtHistoryTop(true);
        return;
      }
      handleDirectionalInput(directionFromDelta(delta));
    };
    const handleTouchEnd = () => {
      const pulling = this.touch?.pulling;
      this.clearTouchTarget();
      this.touch = null;
      if (this.options.spring.endTouch() && pulling && canLoadAtTop()) this.options.loadEarlierMessages();
    };
    const observeHistoryTouchTarget = (target: Node) => {
      if (target === el) return;
      // Touch events remain targeted at the original node even after React replaces it.
      // Keep ordinary connected events on the existing viewport path and only forward
      // events that can no longer reach it through DOM propagation.
      const detached = (handler: (event: TouchEvent) => void) => (event: Event) => {
        if (this.touch?.target === target && !event.composedPath().includes(el)) handler(event as TouchEvent);
      };
      const move = detached(handleTouchMove);
      const end = detached(handleTouchEnd);
      const cancel = detached(handleTouchCancel);
      target.addEventListener("touchmove", move, { passive: false });
      target.addEventListener("touchend", end, { passive: true });
      target.addEventListener("touchcancel", cancel, { passive: true });
      this.touchCleanup = () => {
        target.removeEventListener("touchmove", move);
        target.removeEventListener("touchend", end);
        target.removeEventListener("touchcancel", cancel);
      };
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        event.defaultPrevented
        || event.altKey
        || event.ctrlKey
        || event.metaKey
        || isKeyboardEditableElement(event.target as Element | null)
      ) {
        return;
      }
      if (
        (event.key === "Enter" || event.key === " ")
        && isThreadDisclosureTarget(event.target)
      ) {
        this.options.yieldCameraToUser();
        return;
      }
      if (isKeyboardControl(event.target as Element | null)) return;
      this.inputType = "other";
      handleDirectionalInput(keyboardScrollDirection(event));
    };
    if (this.touch) observeHistoryTouchTarget(this.touch.target);
    el.addEventListener("scroll", handleScroll, { passive: true });
    el.addEventListener("wheel", handleWheel, { passive: true });
    el.addEventListener("touchstart", handleTouchStart, { passive: true });
    el.addEventListener("touchmove", handleTouchMove, { passive: false });
    el.addEventListener("touchend", handleTouchEnd, { passive: true });
    el.addEventListener("touchcancel", handleTouchCancel, { passive: true });
    el.addEventListener("pointerdown", handlePointerDown);
    el.addEventListener("keydown", handleKeyDown);
    this.detach = () => {
      this.clearTouchTarget();
      el.removeEventListener("scroll", handleScroll);
      el.removeEventListener("wheel", handleWheel);
      el.removeEventListener("touchstart", handleTouchStart);
      el.removeEventListener("touchmove", handleTouchMove);
      el.removeEventListener("touchend", handleTouchEnd);
      el.removeEventListener("touchcancel", handleTouchCancel);
      el.removeEventListener("pointerdown", handlePointerDown);
      el.removeEventListener("keydown", handleKeyDown);
    };
  }
}
