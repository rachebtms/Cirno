import { expect, it } from "vitest";
import { collectMcpRuns, mcpRunFromEvent, mcpRunMapByTraceLine } from "@/components/thread/activity/mcp-run-model";

it.each([
  { name: "mcp_research_tools_browser_navigate", mcp_server: "research_tools", mcp_tool: "browser.navigate" },
  { name: "mcp_research_tools_browser_navigate", mcp_server: "research", mcp_tool: "tools_browser_navigate" },
  { name: `mcp_${"long".repeat(10)}_digest`, mcp_server: "long".repeat(24), mcp_tool: "search_notes" },
])("uses explicit server/tool identity instead of guessing from $name", event => {
  const payload = { ...event, phase: "end", call_id: "fixture", arguments: {} };
  expect(mcpRunFromEvent(payload)).toMatchObject({ presetName: event.mcp_server, toolName: event.mcp_tool, status: "done" });
  const message = { id: "fixture", role: "tool" as const, kind: "trace" as const, content: `${event.name}()`, createdAt: 1, toolEvents: [payload] };
  expect(collectMcpRuns([message])[0]).toMatchObject({ presetName: event.mcp_server, toolName: event.mcp_tool });
  expect([...mcpRunMapByTraceLine(message).values()][0]).toMatchObject({ presetName: event.mcp_server, toolName: event.mcp_tool });
});

it("retains legacy name-only replay when no explicit identity exists", () => {
  expect(mcpRunFromEvent({ name: "mcp_browserbase_browser_navigate", phase: "end", call_id: "legacy", arguments: {} }))
    .toMatchObject({ presetName: "browserbase", toolName: "browser_navigate" });
});
