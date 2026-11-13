import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ThreadComposer } from "@/components/thread/ThreadComposer";
import type { SlashCommand } from "@/lib/contracts/commands";

const commands: SlashCommand[] = [
  { command: "/help", title: "Help", description: "", icon: "circle-help", lifecycle: "side_channel", acceptsArgs: false },
  { command: "/model", title: "Model", description: "", icon: "brain", lifecycle: "side_channel", acceptsArgs: true },
  { command: "/goal", title: "Goal", description: "", icon: "target", lifecycle: "agent_turn_with_args", acceptsArgs: true },
  { command: "/stop", title: "Stop", description: "", icon: "square", lifecycle: "stop_active_turn", acceptsArgs: false },
  { command: "/consolidate", title: "Consolidate", description: "", icon: "archive", lifecycle: "side_channel", acceptsArgs: true, aliases: ["/compact", "/dream"] },
  { command: "/pairing", title: "Legacy pairing", description: "", icon: "shield", lifecycle: "side_channel", acceptsArgs: true, hidden: true },
];

it.each(["/help", "/model Lab  DeepSeek", "/goal", "/stop unexpected", "/pairing list"])("sends control input without a configured model: %s", content => {
  const send = vi.fn(), stop = vi.fn();
  render(<ThreadComposer onSend={send} onStop={stop} modelNeedsSetup slashCommands={commands} />);
  const input = screen.getByRole("textbox", { name: "Message input" });
  fireEvent.change(input, { target: { value: content } });
  fireEvent.submit(input.closest("form")!);
  expect(send).toHaveBeenCalledWith(content, undefined, { sideChannel: true });
  expect(stop).not.toHaveBeenCalled();
});

it("keeps real goal requests behind model setup", () => {
  const send = vi.fn();
  render(<ThreadComposer onSend={send} modelNeedsSetup slashCommands={commands} />);
  const input = screen.getByRole("textbox", { name: "Message input" });
  fireEvent.change(input, { target: { value: "/goal read this paper" } });
  fireEvent.submit(input.closest("form")!);
  expect(send).not.toHaveBeenCalled();
});

it("sends a legacy consolidation alias beside an active turn without making it guidance", () => {
  const send = vi.fn();
  render(<ThreadComposer onSend={send} isStreaming slashCommands={commands} />);
  const input = screen.getByRole("textbox", { name: "Message input" });
  fireEvent.change(input, { target: { value: "/compact\tretry source-1" } });
  fireEvent.submit(input.closest("form")!);
  expect(send).toHaveBeenCalledWith("/compact\tretry source-1", undefined, { sideChannel: true });
  expect(screen.queryByRole("group", { name: "Waiting to send" })).not.toBeInTheDocument();
});

it("offers all commands in the scrollable menu while excluding retired entries", () => {
  const extras = Array.from({ length: 12 }, (_, n) => ({ ...commands[0], command: `/audit${n}`, title: `Audit ${n}` }));
  render(<ThreadComposer onSend={vi.fn()} slashCommands={[...commands, ...extras]} />);
  fireEvent.change(screen.getByRole("textbox", { name: "Message input" }), { target: { value: "/" } });
  const menu = screen.getByRole("listbox", { name: "Slash commands" });
  expect(within(menu).getAllByRole("option")).toHaveLength(17);
  expect(within(menu).getByRole("option", { name: /\/audit11/ })).toBeInTheDocument();
  expect(within(menu).queryByText("Legacy pairing")).not.toBeInTheDocument();
});
