import { useLayoutEffect } from "react";
import { isViewportZoomed } from "@/lib/visual-viewport";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { isKeyboardEditableElement } from "@/components/thread/viewport/input-geometry";
import { SOFT_KEYBOARD_MIN_INSET_PX } from "@/components/thread/viewport/geometry";

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
    let layoutWidth = window.innerWidth;
    let expandedHeight = Math.max(window.innerHeight, viewport.height);
    const update = () => {
      cancelAnimationFrame(focusFrame);
      // Pinch zoom pans the existing layout; it must not reflow it or chase the
      // user's magnified viewport. Resume fitting when the scale returns to 1.
      if (isViewportZoomed(viewport)) return;
      if (layoutWidth !== window.innerWidth) {
        layoutWidth = window.innerWidth;
        expandedHeight = window.innerHeight;
      }
      expandedHeight = Math.max(expandedHeight, window.innerHeight, viewport.height);
      // Keep chrome collapsed through a press on Send/Save/Cancel. Restoring
      // it on textarea blur moves the button between pointerdown and pointerup.
      root.classList.toggle("soft-keyboard-open",
        expandedHeight - viewport.height >= SOFT_KEYBOARD_MIN_INSET_PX
        && (isKeyboardEditableElement(document.activeElement)
          || root.classList.contains("soft-keyboard-open")));
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
    const focusOut = () => {
      cancelAnimationFrame(focusFrame);
      // focusout fires before activeElement settles on the next control.
      focusFrame = requestAnimationFrame(update);
    };
    update();
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    window.addEventListener("resize", update);
    document.addEventListener("focusin", update);
    document.addEventListener("focusout", focusOut);
    return () => {
      cancelAnimationFrame(focusFrame);
      window.removeEventListener("resize", update);
      document.removeEventListener("focusin", update);
      document.removeEventListener("focusout", focusOut);
      viewport.removeEventListener("resize", update);
      viewport.removeEventListener("scroll", update);
      root.classList.remove("visual-viewport");
      root.classList.remove("short-visual-viewport");
      root.classList.remove("soft-keyboard-open");
      viewportStyle.removeProperty("--app-viewport-height");
      viewportStyle.removeProperty("--app-viewport-top");
    };
  }, [touch]);
}
