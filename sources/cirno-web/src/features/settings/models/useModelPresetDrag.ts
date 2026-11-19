import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type PointerEvent } from "react";

interface PresetDrag {
  key: string;
  surface: HTMLElement;
  pointerId: number;
  startY: number;
  pointerY: number;
  grabOffset: number;
  active: boolean;
  keys: string[];
  keySignature: string;
}

export function useModelPresetDrag({
  keys, disabled, onReorder,
}: {
  keys: string[];
  disabled: boolean;
  onReorder: (keys: string[]) => void;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const drag = useRef<PresetDrag | null>(null);
  const frame = useRef<number | undefined>(undefined);
  const suppressClick = useRef(false);
  const positions = useRef<Map<string, DOMRect> | null>(null);
  const animations = useRef(new Map<string, Animation>());
  const [preview, setPreview] = useState<{ key: string; keys: string[] } | null>(null);
  const keySignature = JSON.stringify(keys);

  const surfaces = () => Array.from(
    listRef.current?.querySelectorAll<HTMLElement>("[data-preset-sort-surface]") ?? [],
  );
  const rememberPositions = () => {
    positions.current = new Map(surfaces().map((element) => [
      element.dataset.presetSortSurface!, element.getBoundingClientRect(),
    ]));
    for (const animation of animations.current.values()) animation.cancel();
    animations.current.clear();
  };
  const followPointer = () => {
    const current = drag.current;
    if (!current?.active) return;
    const surface = current.surface;
    const top = surface.parentElement!.getBoundingClientRect().top;
    surface.style.transform = `translateY(${current.pointerY - current.grabOffset - top}px)`;
  };
  const trackPointer = () => {
    followPointer();
    frame.current = requestAnimationFrame(trackPointer);
  };

  useLayoutEffect(() => {
    // Live settings may remove or reorder cards while the pointer is down.
    // Retire the old gesture before its frame touches a detached surface or
    // its eventual pointer-up submits keys from an obsolete call order.
    if (drag.current && (disabled || drag.current.keySignature !== keySignature)) {
      finish(false);
      return;
    }
    const previous = positions.current;
    if (!previous) return;
    positions.current = null;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    for (const element of surfaces()) {
      const key = element.dataset.presetSortSurface!;
      const dragging = key === drag.current?.key && drag.current.active;
      if (!dragging) element.style.transform = "";
      const before = previous.get(key);
      if (!before || reduceMotion || typeof element.animate !== "function") continue;
      const after = element.getBoundingClientRect();
      const offset = dragging ? 0 : before.top - after.top;
      const resized = Math.abs(before.height - after.height) >= 0.5;
      if (Math.abs(offset) < 0.5 && !resized) continue;
      // Animate visual size, not layout height, so section headings stay still.
      // Pointer tracking owns the dragged card's translation throughout.
      const from: Keyframe = { scale: `1 ${before.height / after.height}` };
      const to: Keyframe = { scale: "1 1" };
      if (!dragging) {
        from.transform = `translateY(${offset}px)`;
        to.transform = "translateY(0)";
      }
      const animation = element.animate(
        [from, to],
        { duration: 240, easing: "cubic-bezier(0.2, 0, 0, 1)" },
      );
      animations.current.set(key, animation);
      animation.addEventListener("finish", () => {
        if (animations.current.get(key) === animation) animations.current.delete(key);
      }, { once: true });
    }
    followPointer();
  }, [preview, disabled, keySignature]);

  useEffect(() => () => {
    if (frame.current !== undefined) cancelAnimationFrame(frame.current);
    for (const animation of animations.current.values()) animation.cancel();
  }, []);

  const finish = (save: boolean) => {
    const current = drag.current;
    if (!current) return;
    if (frame.current !== undefined) cancelAnimationFrame(frame.current);
    if (current.active) rememberPositions();
    drag.current = null;
    if (listRef.current?.hasPointerCapture(current.pointerId)) {
      listRef.current.releasePointerCapture(current.pointerId);
    }
    if (!current.active) return;
    setPreview(null);
    if (save && !disabled) onReorder(current.keys);
  };

  return {
    listRef,
    previewKeys: preview?.keys ?? keys,
    draggedKey: preview?.key,
    start: (event: PointerEvent, key: string) => {
      if (drag.current || disabled || event.button !== 0 || !keys.includes(key)
        || (event.target as HTMLElement).closest('[role="switch"]')) return;
      const surface = surfaces().find((element) => element.dataset.presetSortSurface === key)!;
      drag.current = {
        key, surface, pointerId: event.pointerId, startY: event.clientY, pointerY: event.clientY,
        grabOffset: event.clientY - surface.getBoundingClientRect().top,
        active: false, keys, keySignature,
      };
    },
    listProps: {
      onPointerDownCapture: () => { if (!drag.current) suppressClick.current = false; },
      onPointerMove: (event: PointerEvent<HTMLDivElement>) => {
        const current = drag.current;
        if (!current || current.pointerId !== event.pointerId || disabled) return;
        if (!event.buttons) { finish(false); return; }
        current.pointerY = event.clientY;
        if (!current.active) {
          if (Math.abs(current.pointerY - current.startY) < 5) return;
          rememberPositions();
          current.active = true;
          suppressClick.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
          setPreview({ key: current.key, keys: current.keys });
          trackPointer();
        }
        event.preventDefault();
        const otherRows = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("[data-preset-sort-key]"))
          .filter((element) => element.dataset.presetSortKey !== current.key
            && keys.includes(element.dataset.presetSortKey!));
        const index = otherRows.filter((element) => {
          const rect = element.getBoundingClientRect();
          return current.pointerY > rect.top + rect.height / 2;
        }).length;
        if (index !== current.keys.indexOf(current.key)) {
          rememberPositions();
          const next = current.keys.filter((key) => key !== current.key);
          next.splice(index, 0, current.key);
          current.keys = next;
          setPreview({ key: current.key, keys: next });
        }
        followPointer();
      },
      onPointerUp: (event: PointerEvent) => { if (event.pointerId === drag.current?.pointerId) finish(true); },
      onPointerCancel: (event: PointerEvent) => { if (event.pointerId === drag.current?.pointerId) finish(false); },
      onLostPointerCapture: (event: PointerEvent) => { if (event.pointerId === drag.current?.pointerId) finish(false); },
      onClickCapture: (event: MouseEvent) => {
        if (!suppressClick.current) return;
        event.preventDefault();
        event.stopPropagation();
        suppressClick.current = false;
      },
      onKeyDownCapture: (event: KeyboardEvent) => {
        suppressClick.current = false;
        if (event.key === "Escape" && drag.current?.active) {
          event.preventDefault();
          event.stopPropagation();
          finish(false);
        }
      },
    },
  };
}
