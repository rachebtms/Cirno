import type { ReactNode } from "react";
import type { PromptHistoryNavigation } from "@/hooks/usePromptHistory";
import type { CliAppInfo } from "@/lib/contracts/apps";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type { RetryStatus, UIMessage } from "@/lib/contracts/messages";
import type { SlashCommand } from "@/lib/contracts/commands";

export interface ThreadViewportHandle {
  jumpToUserPrompt: (promptId: string) => void;
  cancelAutoScroll: () => void;
}

export interface ThreadViewportProps {
  messageEditor?: import("../ThreadMessages").MessageEditorSlot;
  messages: UIMessage[];
  navigation?: PromptHistoryNavigation;
  temporary?: boolean;
  isStreaming: boolean;
  /** Optimistic or canonical start time for the active turn, in unix seconds. */
  runStartedAt?: number | null;
  retryStatus?: RetryStatus | null;
  composer?: ReactNode;
  navigationFrame?: HTMLElement | null;
  emptyState?: ReactNode;
  initialLoading?: boolean;
  scrollToBottomSignal?: number;
  activeTurnId?: string | null;
  activeTurnStartedHere?: boolean;
  conversationKey?: string | null;
  conversationReady?: boolean;
  showScrollToBottomButton?: boolean;
  cliApps?: CliAppInfo[];
  mcpPresets?: McpPresetInfo[];
  slashCommands?: SlashCommand[];
  forkBoundaryMessageCount?: number | null;
  hasMoreBefore?: boolean;
  loadingOlder?: boolean;
  olderError?: string | null;
  userMessageOffset?: number;
  onLoadOlder?: () => Promise<void> | void;
  traceDetailScope?: string | null;
  onLoadTraceDetails?: (refs: string[]) => void | Promise<void>;
  onOpenFilePreview?: (path: string) => void;
  onForkFromMessage?: (beforeUserIndex: number) => void;
  onEditMessage?: (message: UIMessage) => void;
  onQuoteSelection?: (text: string) => void;
}
