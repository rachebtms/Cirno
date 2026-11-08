import { useMemo, type ReactNode } from "react";

import { useLogoFallback } from "@/hooks/useLogoFallback";
import { logoFallbackUrls } from "@/lib/provider-brand";
import { cn } from "@/lib/utils";

interface ActivityBrandMarkerProps {
  active: boolean;
  color: string;
  logoUrl?: string | null;
  testId: string;
  children: ReactNode;
}

export function ActivityBrandMarker({ active, color, logoUrl: source, testId, children }: ActivityBrandMarkerProps) {
  const urls = useMemo(() => logoFallbackUrls(source), [source]);
  const { logoUrl, onLogoError, onLogoLoad } = useLogoFallback(urls);
  return (
    <span
      data-testid={testId}
      className={cn(
        "grid h-4 w-4 shrink-0 place-items-center overflow-hidden rounded-mark text-[6.5px] font-semibold text-white",
        active && "animate-pulse",
      )}
      style={{ backgroundColor: logoUrl ? "transparent" : color }}
      aria-hidden
    >
      {logoUrl ? (
        <img src={logoUrl} alt="" decoding="async" loading="lazy" className="h-full w-full object-contain"
          onLoad={onLogoLoad} onError={onLogoError} />
      ) : children}
    </span>
  );
}
