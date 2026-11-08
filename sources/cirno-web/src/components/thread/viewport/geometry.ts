export const NEAR_BOTTOM_PX = 48;
import { HISTORY_HOLD_PX } from "@/components/thread/thread-history-spring";
import { isKeyboardEditableElement } from "./input-geometry";

export const PROMPT_TOP_INSET_PX = 48;

export const HISTORY_PREFETCH_MIN_PX = 160;

export const HISTORY_PREFETCH_MAX_PX = 480;

export const SOFT_KEYBOARD_MIN_INSET_PX = 80;

export interface HistoryScrollAnchor {
  key: string;
  offsetTop: number;
  scrollTop: number;
}

export const THREAD_DISPLAY_UNIT_SELECTOR = "[data-thread-display-unit]";

export function promptTopInset(scroller: HTMLElement): number {
  const padding = Number.parseFloat(getComputedStyle(scroller).scrollPaddingTop);
  return Number.isFinite(padding) ? padding : PROMPT_TOP_INSET_PX;
}

export function historyPrefetchDistance(scroller: HTMLElement): number {
  return Math.min(
    HISTORY_PREFETCH_MAX_PX,
    Math.max(HISTORY_PREFETCH_MIN_PX, scroller.clientHeight / 2),
  );
}

export function visibleHistoryUnit(
  content: HTMLElement,
  viewport: DOMRect,
): HTMLElement | null {
  // Scroll is a hot path. Hit-testing keeps the common case O(1) instead of
  // forcing layout for every mounted message while the trackpad is moving.
  if (typeof document.elementsFromPoint === "function" && viewport.height > 0) {
    const contentBounds = content.getBoundingClientRect();
    const left = Math.max(viewport.left, contentBounds.left);
    const right = Math.min(viewport.right, contentBounds.right);
    const x = left + Math.max(0, right - left) / 2;
    const offsets = [1, Math.min(32, viewport.height / 3), viewport.height / 2];
    for (const offset of offsets) {
      for (const target of document.elementsFromPoint(x, viewport.top + offset)) {
        const unit = target instanceof Element
          ? target.closest<HTMLElement>(THREAD_DISPLAY_UNIT_SELECTOR)
          : null;
        if (unit && content.contains(unit)) return unit;
      }
    }
  }

  // Deterministic fallback for pre-layout states, tests, and older browsers.
  const units = Array.from(
    content.querySelectorAll<HTMLElement>(THREAD_DISPLAY_UNIT_SELECTOR),
  );
  return units.find((unit) => {
    const bounds = unit.getBoundingClientRect();
    return bounds.bottom > viewport.top && bounds.top < viewport.bottom;
  }) ?? units[0] ?? null;
}

export function readSoftKeyboardInsetBottom(container: HTMLElement | null): number {
  // The touch App shell already fits the visual viewport, including portaled
  // composers. Keep the existing local inset only for unfitted/native layouts.
  if (container?.closest("#root.visual-viewport")) return 0;
  const viewport = window.visualViewport;
  if (!viewport) return 0;
  const active = document.activeElement;
  if (!isKeyboardEditableElement(active) || !container?.contains(active)) return 0;
  const layoutHeight = window.innerHeight || document.documentElement.clientHeight;
  const inset = layoutHeight - viewport.height - viewport.offsetTop;
  return inset >= SOFT_KEYBOARD_MIN_INSET_PX ? Math.ceil(inset) : 0;
}

export function setHistoryPresentation(
  scroller: HTMLDivElement | null,
  status: HTMLDivElement | null,
  slot: HTMLDivElement | null,
  distance: number,
): void {
  // A retained inline slot replaces the same amount of presentation travel.
  const travel = distance - (slot ? HISTORY_HOLD_PX : 0);
  if (scroller) scroller.style.transform = travel ? `translateY(${travel}px)` : "";
  status?.style.setProperty("--history-pull", `${distance}px`);
}
