import { createContext, useContext, useLayoutEffect, useRef, useState } from "react";
import type { ComponentPropsWithoutRef } from "react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import "./tab-surface.css";

const TabWidth = createContext<number | null>(null);

/** Layout belongs to a tab; device capabilities and shell layout belong to the window. */
export function TabSurface({ as: Surface = "section", children, className = "", ...props }: ComponentPropsWithoutRef<"section"> & { as?: "section" | "main" }) {
  const ref = useRef<HTMLElement>(null);
  const [width, setWidth] = useState<number | null>(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => {
      const next = element.clientWidth;
      // Hidden retained tabs have no layout. Keep their last width until shown.
      if (next > 0) setWidth(next);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return <Surface {...props} ref={ref} className={`tab-surface ${className}`}>
    <TabWidth.Provider value={width}>{children}</TabWidth.Provider>
  </Surface>;
}

/** Surfaces without an explicit width owner use the window. */
export function useTabCompact(breakpoint: number): boolean {
  const width = useContext(TabWidth);
  const standaloneCompact = useMediaQuery(`(max-width: ${breakpoint - 1}px)`);
  return width === null ? standaloneCompact : width < breakpoint;
}
