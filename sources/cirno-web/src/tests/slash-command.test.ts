import { expect, it } from "vitest";
import { isRegisteredSlashCommand, matchingSlashCommand, slashCommandLifecycle } from "@/lib/slash-command";
import type { SlashCommand } from "@/lib/types";

const commands: SlashCommand[] = [
  { command: "/goal", title: "Goal", description: "Run a goal", icon: "target", acceptsArgs: true, lifecycle: "agent_turn_with_args" },
  { command: "/stop", title: "Stop", description: "Stop current work", icon: "square", acceptsArgs: false, lifecycle: "stop_active_turn" },
];

it("uses the backend's case-insensitive command spelling", () => {
  expect(isRegisteredSlashCommand(" /STOP ", commands)).toBe(true);
  expect(matchingSlashCommand(" /STOP ", commands)?.command).toBe("/stop");
  expect(slashCommandLifecycle(" /GOAL verify the task ", commands)).toBe("agent_turn");
});

it("does not mistake Telegram's bot suffix for command arguments", () => {
  expect(slashCommandLifecycle("/GOAL@CirnoBot", commands)).toBe("side_channel");
  expect(slashCommandLifecycle("/GOAL@CirnoBot verify the task", commands)).toBe("agent_turn");
  expect(slashCommandLifecycle("/STOP@CirnoBot", commands)).toBe("stop_active_turn");
});

it("keeps invalid arguments for server validation without starting a model turn", () => {
  expect(isRegisteredSlashCommand("/STOP unexpected", commands)).toBe(true);
  expect(matchingSlashCommand("/STOP unexpected", commands)).toBeNull();
  expect(isRegisteredSlashCommand("/unknown", commands)).toBe(false);
});
