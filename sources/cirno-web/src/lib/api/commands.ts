/** Commands operations for the versioned Cirno API. */

import type {
  SlashCommand,
  SlashCommandLifecycle,
} from "@/lib/contracts/commands";
import { API_READ_TIMEOUT_MS, request } from "./transport";

export const SLASH_COMMAND_LIFECYCLES = new Set<SlashCommandLifecycle>([
  "side_channel",
  "finalize_active_turn",
  "stop_active_turn",
  "agent_turn",
  "agent_turn_with_args",
]);

export function isSlashCommandLifecycle(
  value: unknown,
): value is SlashCommandLifecycle {
  return (
    typeof value === "string" &&
    SLASH_COMMAND_LIFECYCLES.has(value as SlashCommandLifecycle)
  );
}

export async function listSlashCommands(
  token: string,
  base: string = "",
): Promise<SlashCommand[]> {
  type Row = {
    command: string;
    title: string;
    description: string;
    icon: string;
    arg_hint?: string;
    lifecycle?: unknown;
    accepts_args?: unknown;
  };
  const body = await request<{ commands: Row[] }>(
    `${base}/v0/commands`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
  return body.commands.flatMap((command) => {
    if (!isSlashCommandLifecycle(command.lifecycle)) return [];
    return [
      {
        command: command.command,
        title: command.title,
        description: command.description,
        icon: command.icon,
        argHint: command.arg_hint ?? "",
        lifecycle: command.lifecycle,
        acceptsArgs: command.accepts_args === true,
      },
    ];
  });
}
