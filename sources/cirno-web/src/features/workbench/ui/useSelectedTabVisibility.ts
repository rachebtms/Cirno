import { useLayoutEffect, useRef } from "react";

function selectedTab(strip: HTMLDivElement, id: string | null) {
  return [...strip.querySelectorAll<HTMLElement>("[data-reorder-id]")]
    .find(element => element.dataset.reorderId === id);
}

/** Scroll only this strip's clipped edge; visible tabs and other groups stay put. */
function reveal(strip: HTMLDivElement, tab: HTMLElement) {
  const bounds = strip.getBoundingClientRect(), item = tab.getBoundingClientRect();
  const start = bounds.left + strip.clientLeft, end = start + strip.clientWidth;
  const delta = item.width > strip.clientWidth || item.left < start
    ? item.left - start : item.right > end ? item.right - end : 0;
  if (delta) strip.scrollBy({ left: delta, behavior: "instant" });
}

export function useSelectedTabVisibility(selected: string | null, activation: number | null) {
  const viewport = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const strip = viewport.current, tab = strip && selectedTab(strip, selected);
    if (!strip || !tab) return;
    const show = () => reveal(strip, tab);
    show();
    const observer = new ResizeObserver(show);
    observer.observe(strip); observer.observe(tab);
    return () => observer.disconnect();
  }, [selected]);
  useLayoutEffect(() => {
    const strip = viewport.current, tab = strip && selectedTab(strip, selected);
    if (activation !== null && strip && tab) reveal(strip, tab);
  }, [activation, selected]);
  return viewport;
}
