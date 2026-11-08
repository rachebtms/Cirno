import { WebSearchRun } from "@/components/thread/activity/WebSearchRun";
import { webSearchRunsByTraceLine } from "@/components/thread/activity/web-search-model";
import type { CliAppInfo } from "@/lib/contracts/apps";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type { UIMessage } from "@/lib/contracts/messages";
import { canonicalToolTrace } from "@/lib/tool-traces";
import {
  type ReactNode
} from "react";
import { ActivityTraceList } from "./ActivityTraceList";
import { CliRunGroup } from "./CliRunRows";
import { McpRunGroup } from "./McpRunRows";
import { traceLines } from "./activity-entries";
import { cliRunMapByTraceLine, parseCliRunTrace } from "./cli-run-model";
import { genericToolStateByTraceLine } from "./generic-tool-state";
import { mcpRunMapByTraceLine, parseMcpRunTrace } from "./mcp-run-model";

export function ActivityTraceTimeline({
  message,
  active,
  cliAppsByName,
  mcpPresetsByName,
}: {
  message: UIMessage;
  active: boolean;
  cliAppsByName: Map<string, CliAppInfo>;
  mcpPresetsByName: Map<string, McpPresetInfo>;
}) {
  const lines = traceLines(message);
  const cliRunsByLine = cliRunMapByTraceLine(message);
  const mcpRunsByLine = mcpRunMapByTraceLine(message);
  const webSearchRunsByLine = webSearchRunsByTraceLine(message.toolEvents ?? []);
  const genericStateByLine = genericToolStateByTraceLine(message);
  const renderedRunKeys = new Set<string>();
  const items: ReactNode[] = [];
  let normalLines: string[] = [];

  const flushNormalLines = (suffix: string) => {
    if (!normalLines.length) return;
    items.push(
      <ActivityTraceList
        key={`${message.id}:trace:${suffix}`}
        lines={normalLines}
        active={active}
        stateByLine={genericStateByLine}
      />,
    );
    normalLines = [];
  };

  lines.forEach((line, index) => {
    const traceKey = canonicalToolTrace(line);
    const webSearchRun = webSearchRunsByLine.get(traceKey);
    if (webSearchRun) {
      flushNormalLines(String(index));
      renderedRunKeys.add(webSearchRun.key);
      items.push(
        <WebSearchRun
          key={`${message.id}:web-search:${webSearchRun.key}:${index}`}
          run={webSearchRun}
          turnActive={active}
        />,
      );
      return;
    }

    const cliRun = cliRunsByLine.get(traceKey) ?? parseCliRunTrace(line);
    if (cliRun) {
      flushNormalLines(String(index));
      renderedRunKeys.add(cliRun.key);
      items.push(
        <CliRunGroup
          key={`${message.id}:cli:${cliRun.key}:${index}`}
          runs={[cliRun]}
          active={active}
          cliAppsByName={cliAppsByName}
        />,
      );
      return;
    }

    const mcpRun = mcpRunsByLine.get(traceKey) ?? parseMcpRunTrace(line);
    if (mcpRun) {
      flushNormalLines(String(index));
      renderedRunKeys.add(mcpRun.key);
      items.push(
        <McpRunGroup
          key={`${message.id}:mcp:${mcpRun.key}:${index}`}
          runs={[mcpRun]}
          active={active}
          mcpPresetsByName={mcpPresetsByName}
        />,
      );
      return;
    }

    normalLines.push(line);
  });

  flushNormalLines("tail");

  for (const run of webSearchRunsByLine.values()) {
    if (renderedRunKeys.has(run.key)) continue;
    items.push(
      <WebSearchRun
        key={`${message.id}:web-search:${run.key}:event`}
        run={run}
        turnActive={active}
      />,
    );
  }
  for (const run of cliRunsByLine.values()) {
    if (renderedRunKeys.has(run.key)) continue;
    items.push(
      <CliRunGroup
        key={`${message.id}:cli:${run.key}:event`}
        runs={[run]}
        active={active}
        cliAppsByName={cliAppsByName}
      />,
    );
  }
  for (const run of mcpRunsByLine.values()) {
    if (renderedRunKeys.has(run.key)) continue;
    items.push(
      <McpRunGroup
        key={`${message.id}:mcp:${run.key}:event`}
        runs={[run]}
        active={active}
        mcpPresetsByName={mcpPresetsByName}
      />,
    );
  }

  if (!items.length) return null;
  return (
    <>
      {items}
    </>
  );
}
