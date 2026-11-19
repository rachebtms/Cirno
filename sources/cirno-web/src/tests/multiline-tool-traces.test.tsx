import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ActivityTraceTimeline } from "@/components/thread/activity/ActivityTraceTimeline";
import { describeTraceLine } from "@/components/thread/activity/trace-activity-model";
import i18n from "@/i18n";
import { canonicalToolTrace } from "@/lib/tool-traces";

const cases = [
  { name: "mcp_fixture_browser_click", args: { element: "Submit", ref: "button" }, label: "Clicked Submit" },
  { name: "apps__run", args: { name: "fixture", args: ["status"] }, label: "Used Fixture, status" },
  { name: "files__read", args: { path: "fixture.txt" }, label: "Read file fixture.txt" },
  { name: "web__search", args: { query: "fixture" }, label: "Searched the web, fixture" },
] as const;

it.each(cases.flatMap(tool => [false, true].map(structured => ({ ...tool, structured }))))("recognizes and matches multiline $name arguments (structured: $structured)", ({ name, args, label, structured }) => {
  const multiline = `${name}(${JSON.stringify(args, null, 2)})`;
  const compact = `${name}(${JSON.stringify(args)})`;
  expect(canonicalToolTrace(multiline)).toBe(canonicalToolTrace(compact));
  render(<ActivityTraceTimeline message={{ id: "fixture", role: "tool", kind: "trace", content: multiline, traces: [multiline], createdAt: 1,
    ...(structured ? { toolEvents: [{ name, call_id: "fixture", phase: "end", arguments: args }] } : {}) }}
    active={false} cliAppsByName={new Map()} mcpPresetsByName={new Map()} />);
  const row = (screen.queryByLabelText(label) ?? screen.getByText(label)).closest('[data-testid="activity-step"]');
  expect(row).toBeInTheDocument();
  expect(screen.getAllByTestId("activity-step")).toHaveLength(1);
});

it.each([
  { name: "shell__exec", args: { command: "echo fixture" }, expected: { label: "Ran command", detail: "echo fixture" } },
  { name: "web__fetch", args: { url: "https://example.org/docs?token=private" }, expected: { label: "Read", detail: "example.org/docs" } },
])("retains the semantic $name description with pretty-printed arguments", ({ name, args, expected }) => {
  expect(describeTraceLine(`${name}(${JSON.stringify(args, null, 2)})`, "done", i18n.t)).toMatchObject(expected);
});
