import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

/** Pointer ordering shared by the Launcher and tab strip. Touch holds preserve scrolling. */
export function useStripReorder(ids: string[], move: (id: string, target: string) => void, transfer?: (id: string, group: string, before?: string) => void) {
  const current = useRef({ ids, move, transfer });
  current.current = { ids, move, transfer };
  const cleanup = useRef(() => {});
  const suppressClick = useRef(false);
  const [dragged, setDragged] = useState<string | null>(null);
  useEffect(() => () => cleanup.current(), []);
  const onPointerDownCapture = (event: PointerEvent<HTMLElement>) => {
    if (event.button !== 0 || (event.target as HTMLElement).closest(".workbench-tab-close")) return;
    const item = (event.target as HTMLElement).closest<HTMLElement>("[data-reorder-id]");
    if (!item?.dataset.reorderId) return;
    cleanup.current();
    suppressClick.current = false;
    const container = event.currentTarget;
    const id = item.dataset.reorderId;
    const pointerId = event.pointerId;
    const x = event.clientX, y = event.clientY;
    let started = false;
    const start = () => {
      started = true;
      suppressClick.current = true;
      setDragged(id);
      container.setPointerCapture(pointerId);
    };
    const timer = event.pointerType === "touch" ? window.setTimeout(start, 350) : undefined;
    const finish = () => {
      window.clearTimeout(timer);
      if (container.hasPointerCapture(pointerId)) container.releasePointerCapture(pointerId);
      window.removeEventListener("pointermove", motion);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", finish);
      window.removeEventListener("touchmove", preventScroll);
      setDragged(null);
      cleanup.current = () => {};
    };
    const preventScroll = (event: TouchEvent) => { if (started) event.preventDefault(); };
    const motion = (event: globalThis.PointerEvent) => {
      if (event.pointerId !== pointerId) return;
      if (!started && Math.hypot(event.clientX - x, event.clientY - y) > 6) {
        if (timer !== undefined) { finish(); return; }
        start();
      }
      if (!started) return;
      event.preventDefault();
      const hit = document.elementFromPoint(event.clientX, event.clientY);
      const target = hit?.closest<HTMLElement>("[data-reorder-id]");
      const group = hit?.closest<HTMLElement>("[data-tab-group]")?.dataset.tabGroup;
      if (group !== undefined && current.current.transfer) current.current.transfer(id, group, target?.dataset.reorderId);
      else if (target && container.contains(target) && target.dataset.reorderId !== id) current.current.move(id, target.dataset.reorderId!);
    };
    window.addEventListener("pointermove", motion, { passive: false });
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", finish);
    window.addEventListener("touchmove", preventScroll, { passive: false });
    cleanup.current = finish;
  };
  const onKeyDownCapture = (event: KeyboardEvent<HTMLElement>) => {
    if (!event.altKey || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    const id = (event.target as HTMLElement).closest<HTMLElement>("[data-reorder-id]")?.dataset.reorderId;
    if (!id) return;
    const direction = ["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 1;
    const target = current.current.ids[current.current.ids.indexOf(id) + direction];
    event.preventDefault();
    event.stopPropagation();
    if (target) current.current.move(id, target);
  };
  return { dragged, handlers: { onPointerDownCapture, onKeyDownCapture,
    onClickCapture: (event: React.MouseEvent<HTMLElement>) => {
      if (suppressClick.current) { event.preventDefault(); event.stopPropagation(); suppressClick.current = false; }
    } } };
}
