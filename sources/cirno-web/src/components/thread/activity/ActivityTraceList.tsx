import {
  CompletedTaskIcon,
  ToolRunIcon,
  WebSearchIcon
} from "@/components/icons/product-icons";
import { ActivityStep } from "@/components/thread/activity/ActivityStep";
import { GenericToolRun } from "@/components/thread/activity/GenericToolRun";
import { WebActivityRow } from "@/components/thread/activity/WebActivityRow";
import {
  formatActivityTarget,
  toolActivityDetails
} from "@/components/thread/activity/activity-text";
import {
  canGroupGenericToolRuns,
  parseGenericToolTrace,
  type GenericToolRunItem,
  type GenericToolStatus,
} from "@/components/thread/activity/generic-tool-model";
import {
  describeTraceLine,
} from "@/components/thread/activity/trace-activity-model";
import { canonicalToolTrace } from "@/lib/tool-traces";
import { Clock3, Layers } from "lucide-react";
import {
  type ReactNode
} from "react";
import { useTranslation } from "react-i18next";
import { GenericToolState } from "./generic-tool-state";

export function ActivityTraceList({
  lines,
  active,
  stateByLine,
}: {
  lines: string[];
  active: boolean;
  stateByLine?: Map<string, GenericToolState>;
}) {
  const items: ReactNode[] = [];
  let genericItems: GenericToolRunItem[] = [];

  const flushGenericItems = (suffix: string) => {
    if (!genericItems.length) return;
    items.push(
      <GenericToolRun
        key={`generic-tool:${genericItems[0].trace.groupKey}:${suffix}`}
        items={genericItems}
      />,
    );
    genericItems = [];
  };

  lines.forEach((line, index) => {
    const trace = parseGenericToolTrace(line);
    if (trace) {
      const key = canonicalToolTrace(line);
      const explicitState = stateByLine?.get(key);
      const fallbackStatus: GenericToolStatus = active && index === lines.length - 1 ? "running" : "done";
      const item: GenericToolRunItem = {
        trace,
        status: explicitState?.status === "running" && !active ? "done" : explicitState?.status ?? fallbackStatus,
        error: explicitState?.error,
        result: explicitState?.result,
      };
      const previous = genericItems[genericItems.length - 1];
      if (previous && !canGroupGenericToolRuns(previous, item)) flushGenericItems(String(index));
      genericItems.push(item);
      return;
    }

    flushGenericItems(String(index));
    items.push(
      <ActivityTraceRow
        key={`${line}-${index}`}
        line={line}
        active={active && index === lines.length - 1}
        state={stateByLine?.get(canonicalToolTrace(line))}
      />,
    );
  });
  flushGenericItems("tail");

  return (
    <>
      {items}
    </>
  );
}

export function ActivityTraceRow({
  line,
  active,
  state,
}: {
  line: string;
  active: boolean;
  state?: GenericToolState;
}) {
  const { t } = useTranslation();
  const status = state?.status ?? (active ? "running" : "done");
  const trace = describeTraceLine(line, status, t, state?.result);
  const rowActive = status === "running" && active;
  const Icon = trace.icon === "clock" ? Clock3 : (trace.kind === "search"
    ? WebSearchIcon
    : trace.kind === "done"
      ? CompletedTaskIcon
      : trace.kind === "tool"
        ? ToolRunIcon
        : Layers);
  if (trace.url && trace.host) {
    return (
      <WebActivityRow
        title={trace.label}
        href={trace.url}
        host={trace.host}
        displayUrl={trace.detail}
        detailsText={toolActivityDetails(line, state?.result, state?.error)}
        active={rowActive}
        tone={status === "error" ? "error" : status === "done" ? "success" : "active"}
      />
    );
  }
  return (
    <ActivityStep
      icon={Icon}
      active={rowActive && trace.kind !== "done"}
      tone={status === "error" ? "error" : status === "done" ? "success" : "active"}
      label={trace.kind === "search" ? trace.label : formatActivityTarget(t, trace.label, trace.detail)}
      detail={trace.kind === "search" ? trace.detail : trace.aside}
      labelClassName={trace.kind === "search" && trace.detail ? "max-w-[50%]" : undefined}
      detailsText={toolActivityDetails(line, state?.result, state?.error)}
    />
  );
}
