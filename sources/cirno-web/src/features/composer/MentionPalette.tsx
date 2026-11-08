import { INLINE_TOKEN_HIGHLIGHT_COLOR } from "@/components/InlineTokenHighlight";
import {
  floatingItemClassName,
  floatingItemFocusClassName,
  floatingSurfaceVisualClassName,
} from "@/components/ui/floating-surface";
import { useLogoFallback } from "@/hooks/useLogoFallback";
import { logoFallbackUrls } from "@/lib/provider-brand";
import { sessionHandleColor } from "@/lib/session-handle";
import { cn } from "@/lib/utils";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { MentionCandidate, SLASH_PALETTE_CHROME_PX } from "./contracts";
import {
  CliAppMentionPaletteProps,
  useSelectedOptionScroll,
} from "./InlineGuidance";
export function CliAppMentionPalette({
  candidates,
  selectedIndex,
  layout,
  isHero,
  onHover,
  onChoose,
}: CliAppMentionPaletteProps) {
  const { t } = useTranslation();
  const listMaxHeight = Math.max(0, layout.maxHeight - SLASH_PALETTE_CHROME_PX);
  const listRef = useSelectedOptionScroll(selectedIndex);
  const groupedCandidates = (["session", "cli", "mcp"] as const)
    .map((kind) => ({
      kind,
      label:
        kind === "session"
          ? t("thread.composer.mentions.sessionGroup")
          : kind === "cli"
            ? t("thread.composer.mentions.cliGroup")
            : t("thread.composer.mentions.mcpGroup"),
      items: candidates
        .map((candidate, index) => ({ candidate, index }))
        .filter(({ candidate }) => candidate.kind === kind),
    }))
    .filter((group) => group.items.length > 0);
  return (
    <div
      role="listbox"
      aria-label={t("thread.composer.mentions.ariaLabel")}
      style={{ maxHeight: layout.maxHeight }}
      className={cn(
        floatingSurfaceVisualClassName,
        "z-30 overflow-hidden",
        layout.placement === "beside"
          ? "relative col-start-2 row-start-1 w-full"
          : cn(
              "absolute left-1/2 w-[calc(100%-0.5rem)] -translate-x-1/2",
              layout.placement === "above"
                ? "bottom-full mb-2"
                : "top-full mt-2",
            ),
        isHero ? "max-w-[58rem]" : "max-w-[49.5rem]",
      )}
    >
      <div
        ref={listRef}
        className="overflow-y-auto"
        style={{ maxHeight: listMaxHeight }}
      >
        {groupedCandidates.map((group) => (
          <div
            key={group.kind}
            role="group"
            aria-label={group.label}
            className="mt-1.5 first:mt-0"
          >
            <div className="px-2 pb-1 pt-1 text-[12px] font-medium text-muted-foreground/72">
              {group.label}
            </div>
            {group.items.map(({ candidate, index }) => {
              const selected = index === selectedIndex;
              const name = candidate.name;
              const handleColor =
                candidate.kind === "session"
                  ? candidate.mention.id
                    ? sessionHandleColor(candidate.mention.id)
                    : INLINE_TOKEN_HIGHLIGHT_COLOR
                  : undefined;
              const typeLabel =
                candidate.kind === "cli"
                  ? t("thread.composer.mentions.cliBadge")
                  : candidate.kind === "mcp"
                    ? t("thread.composer.mentions.mcpBadge")
                    : t("thread.composer.mentions.sessionBadge");
              const ariaDescription =
                candidate.kind === "cli"
                  ? t("thread.composer.mentions.cliDescription", { name })
                  : candidate.kind === "mcp"
                    ? t("thread.composer.mentions.mcpDescription", { name })
                    : t("thread.composer.mentions.sessionDescription", {
                        name,
                      });
              return (
                <button
                  key={`${candidate.kind}-${name}`}
                  type="button"
                  role="option"
                  data-palette-index={index}
                  aria-selected={selected}
                  aria-label={`@${name} ${candidate.displayName} ${ariaDescription} ${typeLabel}`}
                  onMouseEnter={() => onHover(index)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    onChoose(candidate);
                  }}
                  className={cn(
                    floatingItemClassName,
                    floatingItemFocusClassName,
                    "touch-target flex min-h-10 w-full flex-wrap items-center gap-x-2.5 gap-y-1 px-2.5 py-1.5 text-left transition-colors",
                    selected
                      ? "bg-foreground/[0.055] text-foreground dark:bg-black/[0.12]"
                      : "text-foreground/90 hover:bg-foreground/[0.04]",
                  )}
                >
                  <span
                    className="max-w-full shrink-0 truncate text-[15px] font-normal tracking-normal text-muted-foreground/72"
                    style={{ color: handleColor }}
                  >
                    @{name}
                  </span>
                  <span
                    className={cn(
                      "flex max-w-full flex-1 flex-wrap items-center gap-x-2.5 gap-y-1",
                      candidate.kind === "session"
                        ? "min-w-[min(4rem,100%)]"
                        : "min-w-[min(8rem,100%)]",
                    )}
                  >
                    {candidate.kind !== "session" ? (
                      <MentionCandidateLogo
                        candidate={candidate}
                        selected={selected}
                      />
                    ) : null}
                    <span className="min-w-[min(4rem,100%)] flex-1 truncate text-[15px] font-medium tracking-normal text-foreground">
                      {candidate.displayName}
                    </span>
                    {candidate.kind !== "session" ? (
                      <span
                        className={cn(
                          "ml-2 shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold tracking-normal",
                          candidate.kind === "cli"
                            ? "bg-orange-500/10 text-orange-600 dark:text-orange-300"
                            : "bg-sky-500/10 text-sky-600 dark:text-sky-300",
                        )}
                      >
                        {typeLabel}
                      </span>
                    ) : null}
                  </span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export function MentionCandidateLogo({
  candidate,
  selected,
}: {
  candidate: Extract<MentionCandidate, { kind: "cli" | "mcp" }>;
  selected: boolean;
}) {
  const color = candidate.brandColor || INLINE_TOKEN_HIGHLIGHT_COLOR;
  const logoUrls = useMemo(
    () => logoFallbackUrls(candidate.logoUrl),
    [candidate.logoUrl],
  );
  const { logoUrl, onLogoError, onLogoLoad } = useLogoFallback(logoUrls);

  if (logoUrl) {
    return (
      <span
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center overflow-hidden rounded-compact",
          selected ? "bg-background/55" : "bg-transparent",
        )}
      >
        <img
          src={logoUrl}
          alt=""
          decoding="async"
          loading="lazy"
          className="h-5 w-5 object-contain"
          onLoad={onLogoLoad}
          onError={onLogoError}
        />
      </span>
    );
  }
  return (
    <span
      className="flex h-5 w-5 shrink-0 items-center justify-center rounded-compact text-[7.5px] font-semibold text-white"
      style={{ backgroundColor: color }}
    >
      {candidate.initials}
    </span>
  );
}
