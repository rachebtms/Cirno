import { mcpPresetInitials } from "@/components/CliAppMentionText";
import {
  McpIcon
} from "@/components/icons/product-icons";
import { ActivityStep } from "@/components/thread/activity/ActivityStep";
import {
  formatActivityTarget,
  toolActivityDetails
} from "@/components/thread/activity/activity-text";
import { describeMcpActivity } from "@/components/thread/activity/mcp-activity-model";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import { useTranslation } from "react-i18next";
import { ActivityBrandMarker } from "./ActivityBrandMarker";
import { McpRunSummary } from "./mcp-run-model";

export function McpRunGroup({
  runs,
  active,
  mcpPresetsByName,
}: {
  runs: McpRunSummary[];
  active: boolean;
  mcpPresetsByName: Map<string, McpPresetInfo>;
}) {
  if (runs.length === 0) return null;
  return (
    <>
      {runs.map((run) => (
        <McpRunRow
          key={run.key}
          run={run}
          active={active}
          preset={mcpPresetsByName.get(run.presetName.toLowerCase())}
        />
      ))}
    </>
  );
}

export function McpRunRow({ run, active, preset }: { run: McpRunSummary; active: boolean; preset?: McpPresetInfo }) {
  const { t } = useTranslation();
  const failed = run.status === "error";
  const rowActive = active && run.status === "running";
  const color = failed ? "#DC2626" : preset?.brand_color || "#6D5DF6";
  const displayName = preset?.display_name || run.displayName;
  const activity = describeMcpActivity(
    run.toolName,
    run.args,
    failed ? "error" : rowActive ? "running" : "done",
    t,
  );
  const label = formatActivityTarget(t, activity.action, activity.target ?? "");

  return (
    <ActivityStep
      active={rowActive}
      tone={failed ? "error" : rowActive ? "active" : run.status === "done" ? "success" : "neutral"}
      label={label}
      detailsText={run.detailsText ?? toolActivityDetails(`${run.toolName}(${JSON.stringify(run.args)})`, undefined, run.error)}
      detail={displayName}
      marker={<ActivityBrandMarker active={rowActive} color={color} logoUrl={preset?.logo_url} testId={`activity-mcp-logo-${run.presetName.toLowerCase()}`}>{preset ? mcpPresetInitials(preset).slice(0, 2) : <McpIcon className="h-3 w-3" aria-hidden />}</ActivityBrandMarker>}
    />
  );
}
