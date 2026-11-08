import type { ReactNode } from "react";
import type { CliAppInfo } from "@/lib/contracts/apps";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type { SlashCommand } from "@/lib/contracts/commands";
import type { UIMessage } from "@/lib/contracts/messages";

export interface MessageBubbleProps {
  message: UIMessage;
  editor?: ReactNode;
  assistantBubble?: boolean;
  temporary?: boolean;
  cliApps?: CliAppInfo[];
  mcpPresets?: McpPresetInfo[];
  slashCommands?: SlashCommand[];
  onOpenFilePreview?: (path: string) => void;
}

export interface MessageActionsProps {
  message: UIMessage;
  isTurnStreaming?: boolean;
  onForkFromHere?: () => void;
  onEdit?: () => void;
}
