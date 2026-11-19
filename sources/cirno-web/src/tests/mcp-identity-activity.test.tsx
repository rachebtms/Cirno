import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { AgentActivityCluster } from "@/components/thread/AgentActivityCluster";
import type { McpPresetInfo } from "@/lib/contracts/mcp";

it.each(["start", "end"])("shows the explicit MCP identity in a %s activity row", phase => {
  const preset: McpPresetInfo = { name: "research_tools", display_name: "Research Tools", category: "custom", description: "Fixture", docs_url: "", transport: "streamableHttp", requires: "", note: "", install_supported: true, installed: true, configured: true, available: true, status: "configured", required_fields: [], connection_summary: "" };
  const name = "mcp_research_tools_browser_navigate_d69b66e5";
  const line = `${name}(${JSON.stringify({ url: "https://example.org/docs" })})`;
  render(<AgentActivityCluster messages={[{ id: "fixture", role: "tool", kind: "trace", content: line, traces: [line], createdAt: 1,
    toolEvents: [{ phase, name, call_id: "fixture", arguments: { url: "https://example.org/docs" }, mcp_server: "research_tools", mcp_tool: "browser.navigate" }] }]}
    isTurnStreaming={phase === "start"} hasBodyBelow={false} mcpPresets={[preset]} defaultCollapsed={false} expanded />);
  expect(screen.getByLabelText(`${phase === "start" ? "Opening" : "Opened"} example.org/docs, Research Tools`)).toBeInTheDocument();
  expect(screen.getByTestId("activity-mcp-logo-research_tools")).toBeInTheDocument();
  expect(screen.getAllByTestId("activity-step")).toHaveLength(1);
});
