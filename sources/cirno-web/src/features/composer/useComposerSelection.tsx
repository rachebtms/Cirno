import { requestSkillsRefresh } from "@/lib/skill-events";
import { isRegisteredSlashCommand } from "@/lib/slash-command";
import { useEffect, useMemo } from "react";
import {
  SlashPaletteCommand,
  skillMatchRank,
  slashCommandI18nKey,
} from "./commands";
import type { ComponentInputs } from "./inputs";
import type { useComposerState } from "./useComposerState";

export function useComposerSelection({
  inputs,
  composerState,
}: {
  inputs: ComponentInputs;
  composerState: ReturnType<typeof useComposerState>;
}) {
  const {
    quotedContext,
    modelNeedsSetup,
    onModelBadgeClick,
    isStreaming,
    slashCommands,
    onStop,
    skills,
    modelLabel,
    goalState,
  } = inputs;
  const {
    images,
    value,
    interactionDisabled,
    encoding,
    slashMenuDismissed,
    cursorPosition,
    recentSlashCommands,
    t,
  } = composerState;
  const normalizedQuotedContext = quotedContext?.trim() || null;
  const readyImages = useMemo(
    () =>
      images.filter(
        (img) =>
          img.status === "ready" &&
          (typeof img.dataUrl === "string" || !!img.local),
      ),
    [images],
  );
  const hasErrors = images.some((img) => img.status === "error");
  const isUserShell = value.trimStart().startsWith("!");
  const requiresModelSetup = modelNeedsSetup && !isUserShell;
  const hasComposerContent = value.trim().length > 0 || readyImages.length > 0;
  const canSend =
    !interactionDisabled &&
    !requiresModelSetup &&
    !encoding &&
    !hasErrors &&
    hasComposerContent;
  const canOpenModelSettings = Boolean(
    requiresModelSetup && onModelBadgeClick && !interactionDisabled,
  );
  const canQueueGuidance =
    isStreaming &&
    !isUserShell &&
    !interactionDisabled &&
    !modelNeedsSetup &&
    !encoding &&
    !hasErrors &&
    hasComposerContent &&
    // Without command metadata, let the gateway classify slash input immediately.
    (slashCommands.length > 0
      ? !isRegisteredSlashCommand(value, slashCommands)
      : !value.trimStart().startsWith("/"));
  const slashQuery = useMemo(() => {
    if (interactionDisabled || slashMenuDismissed || !value.startsWith("/"))
      return null;
    const commandToken = value.slice(1);
    if (/\s/.test(commandToken)) return null;
    return commandToken.toLowerCase();
  }, [interactionDisabled, slashMenuDismissed, value]);
  const skillQuery = useMemo(() => {
    if (interactionDisabled || isUserShell || slashMenuDismissed) return null;
    const caret = Math.min(Math.max(cursorPosition, 0), value.length);
    const beforeCaret = value.slice(0, caret);
    const match = /\$([A-Za-z0-9_-]*)$/i.exec(beforeCaret);
    if (!match) return null;
    return {
      end: caret,
      start: match.index,
      text: match[1].toLowerCase(),
    };
  }, [
    cursorPosition,
    interactionDisabled,
    isUserShell,
    slashMenuDismissed,
    value,
  ]);
  const skillMenuActive = skillQuery !== null;
  useEffect(() => {
    // Also refresh an empty menu: skills may have been installed by the agent.
    if (skillMenuActive) requestSkillsRefresh();
  }, [skillMenuActive]);
  const visibleSlashCommands = useMemo(() => {
    if (!(isStreaming && onStop)) return slashCommands;
    const stopCommand = slashCommands.find(
      (command) => command.command === "/stop",
    );
    if (!stopCommand) return slashCommands;
    return [
      stopCommand,
      ...slashCommands.filter((command) => command.command !== "/stop"),
    ];
  }, [isStreaming, onStop, slashCommands]);
  const filteredSlashCommands = useMemo<SlashPaletteCommand[]>(() => {
    if (skillQuery !== null) {
      const query = skillQuery.text;
      return skills
        .filter((skill) => skill.enabled !== false && skill.available)
        .flatMap((skill) => {
          const matchRank = skillMatchRank(skill, query);
          return matchRank === null
            ? []
            : [
                {
                  command: `$${skill.name}`,
                  matchRank,
                  skill,
                },
              ];
        })
        .sort((a, b) => {
          if (a.matchRank !== b.matchRank) return a.matchRank - b.matchRank;
          if (query !== "") return 0;
          const aRecent = recentSlashCommands.indexOf(a.command);
          const bRecent = recentSlashCommands.indexOf(b.command);
          if (aRecent === -1 && bRecent === -1) return 0;
          if (aRecent === -1) return 1;
          if (bRecent === -1) return -1;
          return aRecent - bRecent;
        })
        .slice(0, 8)
        .map(({ command, skill }) => {
          const description = skill.description || skill.name;
          return {
            command,
            title: skill.name,
            description,
            detail: description,
            icon: "brain",
            kind: "skill" as const,
            recent: recentSlashCommands.includes(command),
          };
        });
    }
    if (slashQuery === null) return [];
    const withDetails = visibleSlashCommands
      .filter((command) => {
        if (
          slashQuery === "" &&
          (command.command === "/restart" ||
            (command.command === "/stop" && !(isStreaming && onStop)))
        ) {
          return false;
        }
        const commandKey = slashCommandI18nKey(command.command);
        const title = t(`thread.composer.slash.commands.${commandKey}.title`, {
          defaultValue: command.title,
        });
        const description = t(
          `thread.composer.slash.commands.${commandKey}.description`,
          {
            defaultValue: command.description,
          },
        );
        const haystack = [
          command.command,
          command.title,
          command.description,
          command.argHint ?? "",
          title,
          description,
        ]
          .join(" ")
          .toLowerCase();
        return haystack.includes(slashQuery);
      })
      .map((command) => {
        const commandKey = slashCommandI18nKey(command.command);
        const description = t(
          `thread.composer.slash.commands.${commandKey}.description`,
          {
            defaultValue: command.description,
          },
        );
        let detail = description;
        let badge: string | undefined;
        if (command.command === "/model" && modelLabel) {
          detail = modelLabel;
          badge = t("thread.composer.slash.badges.current");
        } else if (command.command === "/goal") {
          detail = goalState?.active
            ? t("thread.composer.slash.details.goalActive")
            : t("thread.composer.slash.details.goalReady");
        } else if (command.command === "/stop" && isStreaming) {
          detail = t("thread.composer.slash.details.stopRunning");
        } else if (command.command === "/history") {
          detail = t("thread.composer.slash.details.history");
        }
        return {
          ...command,
          detail,
          badge,
          recent: recentSlashCommands.includes(command.command),
        };
      })
      .sort((a, b) => {
        if (isStreaming) {
          if (a.command === "/stop") return -1;
          if (b.command === "/stop") return 1;
        }
        if (slashQuery !== "") return 0;
        const aRecent = recentSlashCommands.indexOf(a.command);
        const bRecent = recentSlashCommands.indexOf(b.command);
        if (aRecent !== -1 || bRecent !== -1) {
          if (aRecent === -1) return 1;
          if (bRecent === -1) return -1;
          return aRecent - bRecent;
        }
        return 0;
      });

    return withDetails.slice(0, 8);
  }, [
    goalState?.active,
    isStreaming,
    modelLabel,
    recentSlashCommands,
    skills,
    skillQuery,
    slashQuery,
    t,
    visibleSlashCommands,
  ]);
  const showSlashMenu = filteredSlashCommands.length > 0;
  return {
    isUserShell,
    showSlashMenu,
    slashQuery,
    filteredSlashCommands,
    skillQuery,
    readyImages,
    normalizedQuotedContext,
    canQueueGuidance,
    hasComposerContent,
    requiresModelSetup,
    canSend,
    hasErrors,
    canOpenModelSettings,
  };
}
