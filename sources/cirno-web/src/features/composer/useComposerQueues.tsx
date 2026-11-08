import {
  cliAppInitials,
  mcpPresetInitials,
} from "@/components/CliAppMentionText";
import { withSkillReferences } from "@/components/SkillReferenceText";
import { matchingSlashCommand } from "@/lib/slash-command";
import { useEffect, useMemo, useState } from "react";
import {
  MentionCandidate,
  SLASH_PALETTE_MAX_HEIGHT_PX,
  SlashPaletteLayout,
} from "./contracts";
import type { ComponentInputs } from "./inputs";
import type { useComposerAttachments } from "./useComposerAttachments";
import type { useComposerSelection } from "./useComposerSelection";
import type { useComposerState } from "./useComposerState";

export function useComposerQueues({
  composerAttachments,
  inputs,
  composerSelection,
  composerState,
}: {
  composerAttachments: ReturnType<typeof useComposerAttachments>;
  inputs: ComponentInputs;
  composerSelection: ReturnType<typeof useComposerSelection>;
  composerState: ReturnType<typeof useComposerState>;
}) {
  const {
    cliAppMention,
    insertableSessionMentions,
    sessionMentionCatalog,
    displayMentionSegments,
    sessionDragInsertion,
    draftText,
    mentionSegments,
  } = composerAttachments;
  const { cliApps, mcpPresets, slashCommands } = inputs;
  const { showSlashMenu, isUserShell, slashQuery, filteredSlashCommands } =
    composerSelection;
  const {
    setSelectedCommandIndex,
    setSelectedCliAppIndex,
    selectedCommandIndex,
    selectedCliAppIndex,
    formRef,
    setSlashMenuDismissed,
    setCliAppMenuDismissed,
  } = composerState;
  const filteredMentionCandidates = useMemo<MentionCandidate[]>(() => {
    if (!cliAppMention) return [];
    const sessionCandidates: MentionCandidate[] = insertableSessionMentions
      .filter((mention) =>
        [mention.name, mention.title]
          .join(" ")
          .toLowerCase()
          .includes(cliAppMention.query),
      )
      .map((mention) => ({
        kind: "session",
        name: mention.name,
        displayName: mention.title || mention.name,
        mention,
      }));
    const sessionNames = new Set(
      sessionMentionCatalog.map((mention) => mention.name.toLowerCase()),
    );
    const cliCandidates: MentionCandidate[] = cliApps
      .filter((app) => app.installed)
      .filter((app) => !sessionNames.has(app.name.toLowerCase()))
      .filter((app) => {
        const haystack = [
          app.name,
          app.display_name,
          app.category,
          app.description,
          app.entry_point,
        ]
          .join(" ")
          .toLowerCase();
        return haystack.includes(cliAppMention.query);
      })
      .map((app) => ({
        kind: "cli",
        name: app.name,
        displayName: app.display_name,
        brandColor: app.brand_color ?? null,
        logoUrl: app.logo_url ?? null,
        initials: cliAppInitials(app),
      }));
    const mcpCandidates: MentionCandidate[] = mcpPresets
      .filter((preset) => preset.installed && preset.configured)
      .filter((preset) => !sessionNames.has(preset.name.toLowerCase()))
      .filter((preset) => {
        const haystack = [
          preset.name,
          preset.display_name,
          preset.category,
          preset.description,
          preset.transport,
        ]
          .join(" ")
          .toLowerCase();
        return haystack.includes(cliAppMention.query);
      })
      .map((preset) => ({
        kind: "mcp",
        name: preset.name,
        displayName: preset.display_name,
        brandColor: preset.brand_color ?? null,
        logoUrl: preset.logo_url ?? null,
        initials: mcpPresetInitials(preset),
      }));
    const groups = [
      { candidates: sessionCandidates, reserved: 4 },
      { candidates: cliCandidates, reserved: 2 },
      { candidates: mcpCandidates, reserved: 2 },
    ];
    let remaining = 8;
    const counts = groups.map(({ candidates, reserved }) => {
      const count = Math.min(candidates.length, reserved);
      remaining -= count;
      return count;
    });
    for (const index of [0, 1, 2]) {
      const extra = Math.min(
        remaining,
        groups[index].candidates.length - counts[index],
      );
      counts[index] += extra;
      remaining -= extra;
    }
    return groups.flatMap(({ candidates }, index) =>
      candidates.slice(0, counts[index]),
    );
  }, [
    cliAppMention,
    cliApps,
    insertableSessionMentions,
    mcpPresets,
    sessionMentionCatalog,
  ]);
  const showCliAppMenu = filteredMentionCandidates.length > 0;
  const showAnyPalette = showSlashMenu || showCliAppMenu;
  const inlineSegments = useMemo(
    () =>
      isUserShell
        ? displayMentionSegments
        : withSkillReferences(displayMentionSegments),
    [displayMentionSegments, isUserShell],
  );
  const slashCommand = matchingSlashCommand(
    sessionDragInsertion?.value ?? draftText,
    slashCommands,
  );
  const hasInlineDecorations =
    isUserShell ||
    slashCommand !== null ||
    inlineSegments.some((segment) => segment.kind !== "text");
  const activeCliMentionApps = useMemo(() => {
    const seen = new Set<string>();
    return mentionSegments.flatMap((segment) => {
      if (segment.kind !== "cli" || seen.has(segment.app.name)) return [];
      seen.add(segment.app.name);
      return [segment.app];
    });
  }, [mentionSegments]);
  const activeMcpPresetMentions = useMemo(() => {
    const seen = new Set<string>();
    return mentionSegments.flatMap((segment) => {
      if (segment.kind !== "mcp" || seen.has(segment.preset.name)) return [];
      seen.add(segment.preset.name);
      return [segment.preset];
    });
  }, [mentionSegments]);
  const [slashPaletteLayout, setSlashPaletteLayout] =
    useState<SlashPaletteLayout>({
      placement: "above",
      maxHeight: SLASH_PALETTE_MAX_HEIGHT_PX,
    });
  useEffect(() => {
    setSelectedCommandIndex(0);
  }, [slashQuery]);
  useEffect(() => {
    setSelectedCliAppIndex(0);
  }, [cliAppMention?.query]);
  useEffect(() => {
    if (selectedCommandIndex >= filteredSlashCommands.length) {
      setSelectedCommandIndex(0);
    }
  }, [filteredSlashCommands.length, selectedCommandIndex]);
  useEffect(() => {
    if (selectedCliAppIndex >= filteredMentionCandidates.length) {
      setSelectedCliAppIndex(0);
    }
  }, [filteredMentionCandidates.length, selectedCliAppIndex]);
  useEffect(() => {
    if (!showAnyPalette) return;

    const dismissOnPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && formRef.current?.contains(target)) return;
      setSlashMenuDismissed(true);
      setCliAppMenuDismissed(true);
    };

    document.addEventListener("pointerdown", dismissOnPointerDown, true);
    return () => {
      document.removeEventListener("pointerdown", dismissOnPointerDown, true);
    };
  }, [showAnyPalette]);
  return {
    showAnyPalette,
    setSlashPaletteLayout,
    filteredMentionCandidates,
    activeCliMentionApps,
    activeMcpPresetMentions,
    showCliAppMenu,
    slashPaletteLayout,
    hasInlineDecorations,
    inlineSegments,
    slashCommand,
  };
}
