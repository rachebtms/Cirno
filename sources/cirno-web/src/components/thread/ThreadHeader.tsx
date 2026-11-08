import { headerControlClassName } from "@/components/thread/header-control";
import {
  TemporaryChatIcon,
} from "@/components/icons/product-icons";
import { Code2, Menu, RefreshCw } from "lucide-react";
import { ThemeToggleIcon } from "@/components/icons/ThemeToggleIcon";
import { type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { SessionHandleLabel } from "@/components/SessionHandleLabel";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { SessionHandle } from "@/lib/contracts/messages";

const controlsClassName = cn(
  "pointer-events-auto flex items-center gap-0.5 rounded-compact bg-background p-px empty:hidden",
  "[&_button]:h-7 [&_button]:w-7 [&_button>svg]:h-3.5 [&_button>svg]:w-3.5",
  "forced-colors:bg-[Canvas] forced-colors:outline forced-colors:outline-1 forced-colors:outline-[ButtonText]",
);

interface ThreadHeaderProps {
  className?: string;
  title: string;
  handle?: SessionHandle | null;
  onToggleSidebar: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  hideDesktopSidebarToggle?: boolean;
  hideSidebarToggle?: boolean;
  hideThemeButton?: boolean;
  hideTitle?: boolean;
  actions?: ReactNode;
  minimal?: boolean;
  promptNavigatorAction?: ReactNode;
  sessionInfoAction?: ReactNode;
  ptcModeEnabled?: boolean;
  onPtcModeEnabledChange?: (enabled: boolean) => void;
  temporaryChatEnabled?: boolean;
  temporaryChatDisabled?: boolean;
  onTemporaryChatEnabledChange?: (enabled: boolean) => void;
}

export function ThreadHeader({
  className,
  title,
  handle = null,
  onToggleSidebar,
  theme,
  onToggleTheme,
  hideDesktopSidebarToggle = false,
  hideSidebarToggle = false,
  hideThemeButton = false,
  hideTitle = false,
  actions,
  minimal = false,
  promptNavigatorAction,
  sessionInfoAction,
  ptcModeEnabled = false,
  onPtcModeEnabledChange,
  temporaryChatEnabled = false,
  temporaryChatDisabled = false,
  onTemporaryChatEnabledChange,
}: ThreadHeaderProps) {
  const { t } = useTranslation();

  return (
    <div
      data-testid="thread-header"
      className={cn(
        "pointer-events-none inset-x-0 top-0 z-30 flex shrink-0 items-center justify-between gap-3 px-3 py-1",
        "[position:var(--thread-header-position,absolute)]",
        minimal && "h-11",
        className,
      )}
    >
      <div
        data-theme-surface
        className={cn(
          controlsClassName,
          "relative min-w-0",
          hideDesktopSidebarToggle && (minimal || hideTitle) && !handle && "@min-[1024px]/cirno-tab:hidden",
        )}
      >
        {!hideSidebarToggle ? (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("thread.header.toggleSidebar")}
            onClick={onToggleSidebar}
            className={cn(
              headerControlClassName,
              hideDesktopSidebarToggle && "@min-[1024px]/cirno-tab:hidden",
            )}
          >
            <Menu className="h-3.5 w-3.5" />
          </Button>
        ) : null}
        {!minimal && !hideTitle ? (
          <div className="flex min-w-0 items-center rounded-md px-1.5 py-1 text-[12px] font-medium text-muted-foreground">
            <span className="max-w-[min(60vw,32rem)] truncate">{title}</span>
          </div>
        ) : null}
        {handle ? (
          <span
            className="flex shrink-0 items-center rounded-md px-1.5 py-1 text-[12px] font-medium"
          >
            <SessionHandleLabel id={handle.id}>
              @{handle.name}
            </SessionHandleLabel>
          </span>
        ) : null}
      </div>

      <div data-theme-surface className={cn(controlsClassName, "ml-auto shrink-0")}>
        {sessionInfoAction}
        {promptNavigatorAction}
        {actions}
        {onPtcModeEnabledChange || ptcModeEnabled ? (
          <TooltipProvider><Tooltip><TooltipTrigger asChild>
            <Button type="button" variant="ghost" size="icon"
              aria-label={t("ptc.title")} aria-pressed={ptcModeEnabled}
              disabled={temporaryChatDisabled}
              onClick={onPtcModeEnabledChange ? () => onPtcModeEnabledChange(!ptcModeEnabled) : undefined}
              className={cn(headerControlClassName,
                ptcModeEnabled && "bg-default text-foreground")}
            ><Code2 aria-hidden className="h-3.5 w-3.5" /></Button>
          </TooltipTrigger><TooltipContent side="bottom" align="end" className="max-w-72">
            <div className="font-medium">{t("ptc.title")}</div>
            <div className="mt-1 text-muted-foreground">{t("ptc.description")}</div>
          </TooltipContent></Tooltip></TooltipProvider>
        ) : null}
        {onTemporaryChatEnabledChange ? (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  disabled={temporaryChatDisabled}
                  aria-label={t("temporaryChat.title")}
                  aria-pressed={temporaryChatEnabled}
                  onClick={() => onTemporaryChatEnabledChange(!temporaryChatEnabled)}
                  className={cn(
                    headerControlClassName,
                  )}
                >
                  <TemporaryChatIcon
                    data-testid="temporary-chat-icon"
                    className={cn(
                      "h-4 w-4 motion-safe:transition-colors",
                      temporaryChatEnabled
                        ? "text-[var(--temporary-control-active)] motion-safe:duration-150"
                        : "text-current motion-safe:duration-75",
                    )}
                    aria-hidden
                  />
                </Button>
              </TooltipTrigger>
              <TooltipContent
                side="bottom"
                align="end"
                className="max-w-72 rounded-control border border-border/70 bg-popover px-3 py-2 text-[12px]/[1.4] text-popover-foreground shadow-[0_8px_24px_rgba(15,23,42,0.13)] dark:border-white/10"
              >
                <div className="font-medium">{t("temporaryChat.title")}</div>
                <div className="mt-1 text-muted-foreground">
                  {t("temporaryChat.retention")}
                </div>
                <div className="mt-1 font-medium">
                  {t("temporaryChat.expiration")}
                </div>
                <div className="mt-1 text-muted-foreground">
                  {t("temporaryChat.externalEffects")}
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ) : null}
        <Button variant="ghost" size="icon"
          aria-label={t("thread.header.refresh")}
          title={t("thread.header.refresh")}
          onClick={() => window.location.reload()}
          className={headerControlClassName}>
          <RefreshCw className="h-3.5 w-3.5" />
        </Button>
        {!hideThemeButton ? (
          <ThemeButton
            theme={theme}
            onToggleTheme={onToggleTheme}
            label={t("thread.header.toggleTheme")}
          />
        ) : null}
      </div>
    </div>
  );
}

function ThemeButton({
  theme,
  onToggleTheme,
  label,
  className,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  label: string;
  className?: string;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={label}
      onClick={onToggleTheme}
      className={cn(
        headerControlClassName,
        className,
      )}
    >
      <ThemeToggleIcon theme={theme} />
    </Button>
  );
}
