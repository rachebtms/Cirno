import { useEffect, type RefObject } from "react";

/** Wheel input stays within the strip, with native trackpad distances/inertia. */
export function useHorizontalStripScroll(viewport: RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const strip = viewport.current;
    if (!strip) return;
    const wheel = (event: WheelEvent) => {
      // Trackpad pinch gestures arrive as Ctrl+wheel in Chromium.
      if (event.ctrlKey || event.metaKey) return;
      const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
      if (!delta) return;
      event.preventDefault();
      let unit = 1;
      if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) {
        const style = getComputedStyle(strip);
        unit = Number.parseFloat(style.lineHeight) || Number.parseFloat(style.fontSize);
      } else if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) unit = strip.clientWidth;
      strip.scrollLeft += delta * unit;
    };
    // React's delegated wheel listener is passive; native registration lets
    // this scroll surface consume vertical wheels instead of moving the page.
    strip.addEventListener("wheel", wheel, { passive: false });
    return () => strip.removeEventListener("wheel", wheel);
  }, [viewport]);
}
