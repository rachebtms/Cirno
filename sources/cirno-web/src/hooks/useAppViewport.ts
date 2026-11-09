import { useLayoutEffect } from "react";
import { isViewportZoomed } from "@/lib/visual-viewport";
import { useMediaQuery } from "@/hooks/useMediaQuery";

/** One viewport owner for navigation, workbench composers and ordinary threads. */
export function useAppViewport() {
  const touch = useMediaQuery("(any-pointer: coarse)");
  useLayoutEffect(() => {
    const viewport = window.visualViewport;
    const root = document.getElementById("root");
    if (!touch || !viewport || !root) return;
    // Body portals (for example session search) share the app's viewport owner.
    const viewportStyle = document.documentElement.style;

    let focusFrame = 0;
    const update = () => {
      cancelAnimationFrame(focusFrame);
      // Pinch zoom pans the existing layout; it must not reflow it or chase the
      // user's magnified viewport. Resume fitting when the scale returns to 1.
      if (isViewportZoomed(viewport)) return;
      viewportStyle.setProperty("--app-viewport-height", `${viewport.height}px`);
      // WebKit can report a negative offset after rotating a focused PWA.
      // Do not move the navigation above the top edge with that overscroll.
      viewportStyle.setProperty("--app-viewport-top", `${Math.max(0, viewport.offsetTop)}px`);
      root.classList.add("visual-viewport");
      // Only the keyboard's shortest layouts need a scrollable composer.
      // Normal layouts must let the command and mention palettes overflow.
      root.classList.toggle("short-visual-viewport", viewport.height < 240);
      focusFrame = requestAnimationFrame(() => {
        const active = document.activeElement;
        if (!(active instanceof HTMLElement) || !active.matches('input, textarea, [contenteditable="true"]')) return;
        const rect = active.getBoundingClientRect();
        const top = Math.max(0, viewport.offsetTop);
        if (rect.top < top || rect.bottom > top + viewport.height) {
          active.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
        }
      });
    };
    update();
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    window.addEventListener("resize", update);
    document.addEventListener("focusin", update);
    return () => {
      cancelAnimationFrame(focusFrame);
      window.removeEventListener("resize", update);
      document.removeEventListener("focusin", update);
      viewport.removeEventListener("resize", update);
      viewport.removeEventListener("scroll", update);
      root.classList.remove("visual-viewport");
      root.classList.remove("short-visual-viewport");
      viewportStyle.removeProperty("--app-viewport-height");
      viewportStyle.removeProperty("--app-viewport-top");
    };
  }, [touch]);
}
