import { CapabilityMentionToken } from "@/components/CliAppMentionText";
import {
  INLINE_REFERENCE_HIGHLIGHT_COLOR,
  InlineTokenHighlight,
} from "@/components/InlineTokenHighlight";
import {
  SkillReferenceToken,
  type InlineReferenceSegment,
} from "@/components/SkillReferenceText";
import { SlashCommandText } from "@/components/SlashCommandText";
import { cn } from "@/lib/utils";
import { useLayoutEffect, useRef, type Ref } from "react";
import { SlashPaletteCommand } from "./commands";
import {
  MentionCandidate,
  SlashPaletteLayout,
} from "./contracts";
export function ComposerInlineReferenceOverlay({
  overlayRef,
  segments,
  slashCommand,
  isHero,
  isComposing,
  className,
  ghostRange,
}: {
  overlayRef: Ref<HTMLDivElement>;
  segments: InlineReferenceSegment[];
  slashCommand: string | null;
  isHero: boolean;
  isComposing: boolean;
  className: string;
  ghostRange?: { start: number; end: number } | null;
}) {
  let offset = 0;
  const occurrences = new Map<string, number>();
  return (
    <div
      ref={overlayRef}
      aria-hidden
      className={cn(
        className,
        "pointer-events-none absolute inset-0 z-0 overflow-hidden whitespace-pre-wrap break-words text-foreground",
        // Native IME selection backgrounds can be opaque; keep the mirrored glyphs visible.
        isComposing && "z-20",
      )}
    >
      {segments.map((segment, index) => {
        const start = offset;
        offset += segment.text.length;
        if (segment.kind === "text") {
          const bangPrefix = index === 0 ? /^(\s*)!/.exec(segment.text) : null;
          return (
            <span key={`text-${index}`}>
              {bangPrefix ? (
                <>
                  {bangPrefix[1]}
                  <InlineTokenHighlight
                    testId="composer-shell-prefix"
                    className="font-normal"
                    color={INLINE_REFERENCE_HIGHLIGHT_COLOR}
                  >
                    <span className="opacity-90">!</span>
                  </InlineTokenHighlight>
                  {segment.text.slice(bangPrefix[0].length)}
                </>
              ) : start === 0 && slashCommand ? (
                <>
                  <SlashCommandText
                    command={slashCommand}
                    testId="composer-slash-command"
                  />
                  {segment.text.slice(slashCommand.length)}
                </>
              ) : (
                segment.text
              )}
            </span>
          );
        }
        if (segment.kind === "skill") {
          return (
            <SkillReferenceToken
              key={`skill-${segment.name}-${index}`}
              name={segment.name}
              testId={`composer-skill-reference-${segment.name.toLowerCase()}`}
            />
          );
        }
        const isGhost =
          ghostRange?.start === start && ghostRange.end === offset;
        const identity = `${segment.kind}-${
          segment.kind === "cli"
            ? segment.app.name
            : segment.kind === "mcp"
              ? segment.preset.name
              : segment.mention.session_key
        }`;
        const occurrence = occurrences.get(identity) ?? 0;
        occurrences.set(identity, occurrence + 1);
        return (
          <span
            key={`${identity}-${occurrence}`}
            data-testid={isGhost ? "composer-session-drag-preview" : undefined}
            className={cn(
              isGhost && "opacity-45 transition-opacity duration-100",
            )}
          >
            <CapabilityMentionToken
              segment={segment}
              variant="composer"
              isHero={isHero}
            />
          </span>
        );
      })}
      {segments.at(-1)?.text.endsWith("\n") ? "\u200b" : null}
    </div>
  );
}

export interface SlashCommandPaletteProps {
  commands: SlashPaletteCommand[];
  selectedIndex: number;
  layout: SlashPaletteLayout;
  isHero: boolean;
  onHover: (index: number) => void;
  onChoose: (command: SlashPaletteCommand) => void;
}

export interface CliAppMentionPaletteProps {
  candidates: MentionCandidate[];
  selectedIndex: number;
  layout: SlashPaletteLayout;
  isHero: boolean;
  onHover: (index: number) => void;
  onChoose: (candidate: MentionCandidate) => void;
}

export function useSelectedOptionScroll(selectedIndex: number) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const option = container.querySelector<HTMLElement>(
      `[data-palette-index="${selectedIndex}"]`,
    );
    if (typeof option?.scrollIntoView === "function") {
      option.scrollIntoView({ block: "nearest" });
    }
  }, [selectedIndex]);

  return containerRef;
}
