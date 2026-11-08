import { Button, Popover, Tooltip } from "@heroui/react";
import { useState } from "react";
import { ArrowRightLeft, Hexagon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLogoFallback } from "@/hooks/useLogoFallback";
import { providerBrand } from "@/lib/provider-brand";
import type { ResponseSource } from "@/lib/contracts/messages";
import { cn } from "@/lib/utils";

export function FallbackResponseSources({
  sources,
  className,
  badgeClassName,
}: {
  sources?: ResponseSource[];
  className?: string;
  badgeClassName?: string;
}) {
  const fallbacks = sources?.filter((source) => source.fallback === true) ?? [];
  return (
    fallbacks.length > 0 && (
      <div className={cn("message-response-sources", className)}>
        {fallbacks.map((source) => (
          <ResponseSourceBadge
            key={JSON.stringify(source)}
            source={source}
            className={badgeClassName}
          />
        ))}
      </div>
    )
  );
}

/** Invocation identity is historical evidence, independent of current provider settings. */
function ResponseSourceBadge({
  source,
  className,
}: {
  source: ResponseSource;
  className?: string;
}) {
  const { t } = useTranslation(),
    [open, setOpen] = useState(false);
  const description = t("message.fallbackResponse", { preset: source.preset });
  const brand = providerBrand(source.provider);
  const logo = useLogoFallback(brand?.logoUrls),
    tile = brand?.logoLayout === "tile" && logo.logoUrl === brand.logoUrl;
  return (
    <Popover isOpen={open} onOpenChange={setOpen}>
      <Tooltip isDisabled={open} delay={0}>
        <Tooltip.Trigger
          role="presentation"
          tabIndex={-1}
          className="inline-flex min-w-0"
        >
          <Button
            type="button"
            size="sm"
            variant="ghost"
            aria-label={description}
            className={cn("message-response-source", className)}
          >
            <ArrowRightLeft size={12} aria-hidden />
            <span
              aria-hidden
              className={cn(
                "message-provider-mark",
                logo.logoLoaded && !tile && "bg-white",
              )}
            >
              {logo.logoUrl && (
                <img
                  src={logo.logoUrl}
                  alt=""
                  loading="lazy"
                  decoding="async"
                  referrerPolicy="no-referrer"
                  onLoad={logo.onLogoLoad}
                  onError={logo.onLogoError}
                  className={cn(
                    tile ? "size-4" : "size-3",
                    !logo.logoLoaded && "opacity-0",
                  )}
                />
              )}
              {!logo.logoLoaded && <Hexagon size={14} className="absolute" />}
            </span>
            <span className="min-w-0 truncate">{source.preset}</span>
          </Button>
        </Tooltip.Trigger>
        <Tooltip.Content placement="top" className="message-metadata-popover">
          {description}
        </Tooltip.Content>
      </Tooltip>
      <Popover.Content placement="top" className="message-metadata-popover">
        <Popover.Dialog aria-label={description}>{description}</Popover.Dialog>
      </Popover.Content>
    </Popover>
  );
}
