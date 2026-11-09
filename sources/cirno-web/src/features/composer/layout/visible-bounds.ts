import { isViewportZoomed } from "@/lib/visual-viewport";

export function visualViewportBounds(): {
  top: number;
  bottom: number;
  height: number;
} {
  const viewport = window.visualViewport;
  if (!viewport) {
    return { top: 0, bottom: window.innerHeight, height: window.innerHeight };
  }
  const top = Math.max(0, viewport.offsetTop);
  const height = Math.max(0, viewport.height);
  return { top, bottom: top + height, height };
}

export function getVisibleBounds(el: HTMLElement): {
  top: number;
  bottom: number;
} {
  // The app already follows the visual viewport on touch browsers. Measure
  // its frame in the same coordinates as the composer, not WebKit's pan offset.
  // During pinch zoom the app stops fitting, so use the zoomed viewport again.
  const fittedRoot =
    window.visualViewport && !isViewportZoomed(window.visualViewport)
      ? el.closest("#root.visual-viewport")
      : null;
  const viewport =
    fittedRoot?.getBoundingClientRect() ?? visualViewportBounds();
  let top = viewport.top;
  let bottom = viewport.bottom;
  let parent = el.parentElement;

  while (parent) {
    const style = window.getComputedStyle(parent);
    if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) {
      const rect = parent.getBoundingClientRect();
      top = Math.max(top, rect.top);
      bottom = Math.min(bottom, rect.bottom);
    }
    parent = parent.parentElement;
  }

  return { top, bottom };
}
