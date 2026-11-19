import { WebSearchRun } from "@/components/thread/activity/WebSearchRun";
import { webSearchRunFromEvent } from "@/components/thread/activity/web-search-model";
import type { CliAppInfo } from "@/lib/contracts/apps";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type { UIMessage } from "@/lib/contracts/messages";
import {
  type ReactNode
} from "react";
import { ActivityTraceList } from "./ActivityTraceList";
import { CliRunGroup } from "./CliRunRows";
import { McpRunGroup } from "./McpRunRows";
import { cliRunFromEvent, parseCliRunTrace } from "./cli-run-model";
import { genericToolStateFromEvent } from "./generic-tool-state";
import { mcpRunFromEvent, parseMcpRunTrace } from "./mcp-run-model";
import { activityToolEntries, type ActivityToolEntry } from "./tool-activity-timeline";

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
  const entries = activityToolEntries(message);
  const items: ReactNode[] = [];
  let normal: ActivityToolEntry[] = [];

  const flushNormalLines = (suffix: string) => {
    if (!normal.length) return;
    items.push(
      <ActivityTraceList
        key={`${message.id}:trace:${suffix}`}
        lines={normal.map(entry => entry.line)}
        active={active}
        statesByIndex={normal.map(entry => entry.event ? genericToolStateFromEvent(entry.event) : undefined)}
      />,
    );
    normal = [];
  };

  entries.forEach((entry, index) => {
    const { line, event } = entry;
    const webSearchRun = event ? webSearchRunFromEvent(event) : null;
    if (webSearchRun) {
      flushNormalLines(String(index));
      items.push(
        <WebSearchRun
          key={`${message.id}:web-search:${entry.key}`}
          run={webSearchRun}
          turnActive={active}
        />,
      );
      return;
    }

    const cliRun = event ? cliRunFromEvent(event) : parseCliRunTrace(line);
    if (cliRun) {
      flushNormalLines(String(index));
      items.push(
        <CliRunGroup
          key={`${message.id}:cli:${entry.key}`}
          runs={[cliRun]}
          active={active}
          cliAppsByName={cliAppsByName}
        />,
      );
      return;
    }

    const mcpRun = event ? mcpRunFromEvent(event) : parseMcpRunTrace(line);
    if (mcpRun) {
      flushNormalLines(String(index));
      items.push(
        <McpRunGroup
          key={`${message.id}:mcp:${entry.key}`}
          runs={[mcpRun]}
          active={active}
          mcpPresetsByName={mcpPresetsByName}
        />,
      );
      return;
    }

    normal.push(entry);
  });

  flushNormalLines("tail");

  if (!items.length) return null;
  return (
    <>
      {items}
    </>
  );
}
