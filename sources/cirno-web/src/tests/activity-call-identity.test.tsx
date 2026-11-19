import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { ActivityTraceTimeline } from "@/components/thread/activity/ActivityTraceTimeline";
import i18n from "@/i18n";
import type { ToolProgressEvent } from "@/lib/contracts/activity";
import { formatToolCallTrace, mergeToolProgressEvents } from "@/lib/tool-traces";

const tools = [
  { name: "mcp_fixture_browser_click", arguments: { element: "Submit" } },
  { name: "apps__run", arguments: { name: "fixture", args: ["status"] } },
  { name: "web__search", arguments: { query: "fixture" } },
  { name: "files__read", arguments: { path: "fixture.txt" } },
] as const;

function details(): string[] {
  return screen.getAllByTestId("activity-step").map(row => {
    if (!within(row).queryByTestId("activity-step-details")) {
      fireEvent.click(within(row).getByRole("button", { name: i18n.t("message.expandStep") }));
    }
    return within(row).getByTestId("activity-step-details").textContent ?? "";
  });
}

it.each(tools)("retains separate outcomes for identical $name calls", tool => {
  const events: ToolProgressEvent[] = [
    { ...tool, phase: "end", call_id: "first", result: "first completed" },
    { ...tool, phase: "error", call_id: "second", error: "second failed" },
  ];
  const line = formatToolCallTrace(tool)!;
  render(<ActivityTraceTimeline message={{ id: "fixture", role: "tool", kind: "trace", content: line, traces: [line], toolEvents: events, createdAt: 1 }}
    active cliAppsByName={new Map()} mcpPresetsByName={new Map()} />);
  const text = details();
  expect(text.join("\n")).toContain("first completed");
  expect(text.join("\n")).toContain("second failed");
  if (tool.name !== "files__read") {
    expect(text).toHaveLength(2);
    expect(text[0]).not.toContain("second failed");
    expect(text[1]).not.toContain("first completed");
  }
});

it("keeps structured call order even when identical trace lines have been compacted", () => {
  const tool = tools[0];
  const middle = { ...tool, arguments: { element: "Middle" } };
  const events: ToolProgressEvent[] = [tool, middle, tool].map((call, index) => ({ ...call, phase: "end", call_id: String(index), result: `result-${index}` }));
  render(<ActivityTraceTimeline message={{ id: "ordered", role: "tool", kind: "trace", content: "", traces: [formatToolCallTrace(tool)!, formatToolCallTrace(middle)!], toolEvents: events, createdAt: 1 }}
    active={false} cliAppsByName={new Map()} mcpPresetsByName={new Map()} />);
  const text = details();
  expect(text).toHaveLength(3);
  text.forEach((value, index) => expect(value).toContain(`result-${index}`));
});

it("coalesces phases within a first incoming event batch by call ID", () => {
  const start: ToolProgressEvent = { ...tools[0], phase: "start", call_id: "first" };
  const finish = { ...start, phase: "end", result: "complete" };
  const next = { ...start, call_id: "second" };
  expect(mergeToolProgressEvents(undefined, [start, finish, next])).toEqual([finish, next]);
  expect(mergeToolProgressEvents([], [finish, start])).toEqual([finish]);
});

it.each([tools[0], tools[1]])("does not duplicate a $name record when JSON field order changes", tool => {
  const args = tool.name.startsWith("mcp_") ? { element: "Submit", ref: "button" } : tool.arguments;
  const line = `${tool.name}(${JSON.stringify(Object.fromEntries(Object.entries(args).reverse()))})`;
  render(<ActivityTraceTimeline message={{ id: "reordered", role: "tool", kind: "trace", content: line, traces: [line], createdAt: 1,
    toolEvents: [{ name: tool.name, arguments: args, call_id: "fixture", phase: "end", result: "one result" }] }}
    active={false} cliAppsByName={new Map()} mcpPresetsByName={new Map()} />);
  const text = details();
  expect(text).toHaveLength(1);
  expect(text[0]).toContain("one result");
});
