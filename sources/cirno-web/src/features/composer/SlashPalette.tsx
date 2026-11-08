import { HelpIcon, SkillsIcon } from "@/components/icons/product-icons";
import {
  floatingItemClassName,
  floatingItemFocusClassName,
  floatingSurfaceVisualClassName,
} from "@/components/ui/floating-surface";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import { slashCommandI18nKey } from "./commands";
import {
  BUILTIN_COMMAND_ICONS,
  COMMAND_ICONS,
  SLASH_PALETTE_CHROME_PX,
} from "./contracts";
import {
  SlashCommandPaletteProps,
  useSelectedOptionScroll,
} from "./InlineGuidance";
export function SlashCommandPalette({
  commands,
  selectedIndex,
  layout,
  isHero,
  onHover,
  onChoose,
}: SlashCommandPaletteProps) {
  const { t } = useTranslation();
  const listMaxHeight = Math.max(0, layout.maxHeight - SLASH_PALETTE_CHROME_PX);
  const listRef = useSelectedOptionScroll(selectedIndex);
  return (
    <div
      role="listbox"
      aria-label={t("thread.composer.slash.ariaLabel")}
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
        className="overflow-y-auto pr-0.5"
        style={{ maxHeight: listMaxHeight }}
      >
        {commands.map((command, index) => {
          const Icon =
            command.kind === "skill"
              ? SkillsIcon
              : (BUILTIN_COMMAND_ICONS[command.command] ??
                COMMAND_ICONS[command.icon] ??
                HelpIcon);
          const selected = index === selectedIndex;
          const isSkill = command.kind === "skill";
          const commandKey = slashCommandI18nKey(command.command);
          const title = t(
            `thread.composer.slash.commands.${commandKey}.title`,
            {
              defaultValue: command.title,
            },
          );
          const description = t(
            `thread.composer.slash.commands.${commandKey}.description`,
            {
              defaultValue: command.description,
            },
          );
          return (
            <button
              key={command.command}
              type="button"
              role="option"
              data-palette-index={index}
              aria-selected={selected}
              onMouseEnter={() => onHover(index)}
              onMouseDown={(e) => {
                e.preventDefault();
                onChoose(command);
              }}
              className={cn(
                floatingItemClassName,
                floatingItemFocusClassName,
                "flex min-h-[44px] w-full items-center gap-3 px-3 py-2 text-left transition-colors",
                selected
                  ? "bg-foreground/[0.065] text-foreground dark:bg-white/[0.09]"
                  : "text-foreground/86 hover:bg-foreground/[0.045] dark:hover:bg-white/[0.065]",
              )}
            >
              <span
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center text-muted-foreground transition-colors",
                  selected && "text-foreground",
                )}
              >
                <Icon className="h-4 w-4" />
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-0.5 @min-[640px]/cirno-tab:flex-row @min-[640px]/cirno-tab:items-baseline @min-[640px]/cirno-tab:gap-2">
                <span
                  className={cn(
                    "text-[13.5px] font-semibold tracking-normal text-foreground",
                    isSkill
                      ? "max-w-full shrink-0 break-all @min-[640px]/cirno-tab:max-w-[55%]"
                      : "min-w-0 truncate",
                  )}
                >
                  {title}
                </span>
                <span className="min-w-0 truncate text-[13px] text-muted-foreground">
                  {command.detail || description}
                </span>
              </span>
              {!isSkill || command.badge || command.recent ? (
                <span className="ml-2 flex max-w-[42%] shrink-0 items-center gap-1.5 @min-[640px]/cirno-tab:max-w-none">
                  {command.badge || command.recent ? (
                    <span className="hidden rounded-full bg-foreground/[0.055] px-2 py-1 text-[11px] font-medium text-muted-foreground @min-[640px]/cirno-tab:inline-flex">
                      {command.badge ??
                        t("thread.composer.slash.badges.recent")}
                    </span>
                  ) : null}
                  {!isSkill ? (
                    <span className="font-mono text-[12px] text-muted-foreground/60">
                      {command.argHint
                        ? `${command.command} ${command.argHint}`
                        : command.command}
                    </span>
                  ) : null}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
