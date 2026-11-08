import { cliAppInitials } from "@/components/CliAppMentionText";
import { ActivityStep } from "@/components/thread/activity/ActivityStep";
import {
  compactActivityPath,
  redactShellCommand,
  toolActivityDetails
} from "@/components/thread/activity/activity-text";
import type { CliAppInfo } from "@/lib/contracts/apps";
import { Terminal } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ActivityBrandMarker } from "./ActivityBrandMarker";
import { CliRunSummary, formatCliArgs } from "./cli-run-model";
import { titleFromPresetName } from "./tool-run-events";

export function CliRunGroup({
  runs,
  active,
  cliAppsByName,
}: {
  runs: CliRunSummary[];
  active: boolean;
  cliAppsByName: Map<string, CliAppInfo>;
}) {
  if (runs.length === 0) return null;
  return (
    <>
      {runs.map((run) => (
        <CliRunRow
          key={run.key}
          run={run}
          active={active}
          app={cliAppsByName.get(run.name.toLowerCase())}
        />
      ))}
    </>
  );
}

export function CliRunRow({ run, active, app }: { run: CliRunSummary; active: boolean; app?: CliAppInfo }) {
  const { t } = useTranslation();
  const args = compactActivityPath(redactShellCommand(formatCliArgs(run)));
  const failed = run.status === "error";
  const rowActive = active && run.status === "running";
  const color = failed ? "#DC2626" : app?.brand_color || "#0891B2";
  const displayName = app?.display_name || titleFromPresetName(run.name);
  const label = t(
    `message.${failed ? "cliActivityFailedOne" : rowActive ? "cliActivityRunningOne" : "cliActivityRanOne"}`,
    { name: displayName },
  );

  return (
    <ActivityStep
      active={rowActive}
      tone={failed ? "error" : rowActive ? "active" : run.status === "done" ? "success" : "neutral"}
      label={label}
      detailsText={run.detailsText ?? toolActivityDetails(`${run.name}(${JSON.stringify(run.args)})`, undefined, run.error)}
      detail={args}
      detailClassName="font-mono text-[12px]"
      marker={<ActivityBrandMarker active={rowActive} color={color} logoUrl={app?.logo_url} testId={`activity-cli-logo-${run.name.toLowerCase()}`}>{app ? cliAppInitials(app).slice(0, 2) : <Terminal className="h-3 w-3" aria-hidden />}</ActivityBrandMarker>}
    />
  );
}
