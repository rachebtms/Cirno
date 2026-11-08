import { useLayoutEffect, useRef } from "react";

const HERO_GREETING_KEYS = [
  "thread.empty.greetings.workOn",
  "thread.empty.greetings.start",
  "thread.empty.greetings.build",
  "thread.empty.greetings.tackle",
] as const;

export function HeroGreeting({ text }: { text: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useLayoutEffect(() => {
    const container = containerRef.current;
    const heading = headingRef.current;
    if (!container || !heading) return;

    const fitToWidth = () => {
      heading.style.removeProperty("font-size");
      const availableWidth = container.clientWidth;
      if (availableWidth <= 0) return;

      const naturalWidth = heading.scrollWidth;
      const maximumFontSize = Number.parseFloat(window.getComputedStyle(heading).fontSize);
      if (
        naturalWidth <= availableWidth
        || !Number.isFinite(maximumFontSize)
        || maximumFontSize <= 0
      ) {
        return;
      }

      const fittedFontSize = Math.max(
        12,
        Math.floor(maximumFontSize * ((availableWidth - 2) / naturalWidth) * 100) / 100,
      );
      heading.style.fontSize = `${fittedFontSize}px`;
    };

    fitToWidth();

    let lastObservedWidth = container.clientWidth;
    const resizeObserver = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(([entry]) => {
        const nextWidth = entry?.contentRect.width ?? container.clientWidth;
        if (nextWidth === lastObservedWidth) return;
        lastObservedWidth = nextWidth;
        fitToWidth();
      });
    resizeObserver?.observe(container);
    window.addEventListener("resize", fitToWidth);

    let cancelled = false;
    void document.fonts?.ready.then(() => {
      if (!cancelled) fitToWidth();
    });

    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      window.removeEventListener("resize", fitToWidth);
    };
  }, [text]);

  return (
    <div ref={containerRef} className="min-w-0 w-full max-w-[44rem]">
      <h1
        ref={headingRef}
        data-testid="hero-greeting"
        data-theme-ink
        className="select-none whitespace-nowrap text-[34px] font-normal leading-[1.08] tracking-normal text-foreground @min-[640px]/cirno-tab:text-[48px] @min-[640px]/cirno-tab:leading-tight"
      >
        {text}
      </h1>
    </div>
  );
}

export function randomHeroGreetingKey(): (typeof HERO_GREETING_KEYS)[number] {
  const index = Math.floor(Math.random() * HERO_GREETING_KEYS.length);
  return HERO_GREETING_KEYS[index] ?? HERO_GREETING_KEYS[0];
}
