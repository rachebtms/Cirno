import { useSourceLabel } from "@/features/conversations/catalog/useSourceLabel";
import { Button, ListBox, SearchField, Select } from "@heroui/react";
import { ArrowDown, ArrowUp, Ban, ChevronsUp, Circle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { EVENT_GROUPS } from "./contracts";
import { Hint } from "@/ui/feedback/Hint";
import type { useTrace } from "./useTrace";

type TraceState = ReturnType<typeof useTrace>;
function TraceAction({ label, disabled, onPress, recording, children }: {
  label: string; disabled: boolean; onPress: () => void; recording?: boolean; children: ReactNode;
}) {
  return <Hint content={label}><Button isIconOnly size="sm" variant="ghost" className={recording ? "trace-recording" : undefined}
    aria-label={label} isDisabled={disabled} onPress={onPress}>{children}</Button></Hint>;
}

export function TraceToolbar({ trace, query, onQuery }: { trace: TraceState; query: string; onQuery: (value: string) => void }) {
  const { t } = useTranslation();
  const sourceLabel = useSourceLabel();
  const running = Boolean(trace.info?.running);
  const sources = [...new Set([...(trace.page?.sources ?? []), ...(trace.source ? [trace.source] : [])])];
  return <div className="trace-toolbar">
    <div className="trace-recording-actions">
      <TraceAction recording={running} label={t(running ? "workspace.debug.pause" : "workspace.debug.start")} disabled={trace.busy || !trace.info}
        onPress={() => void trace.control(running ? "pause" : "start")}><Circle size={14} fill={running ? "currentColor" : "none"} /></TraceAction>
      <TraceAction label={t("workspace.debug.clear")} disabled={trace.busy || !trace.info} onPress={() => void trace.control("clear")}><Ban size={14} /></TraceAction>
      <TraceAction label={t("workspace.debug.refresh")} disabled={trace.busy} onPress={trace.refresh}><RefreshCw size={14} /></TraceAction>
    </div>
    <Select aria-label={t("workspace.debug.type")} value={trace.kind} onChange={key => { if (key !== null) trace.setKind(String(key)); }}>
      <Select.Trigger><Select.Value>{t(trace.kind === "all" ? "workspace.debug.all" : `workspace.debug.kinds.${trace.kind}`)}</Select.Value><Select.Indicator /></Select.Trigger>
      <Select.Popover><ListBox>{["all", ...EVENT_GROUPS].map(id => <ListBox.Item key={id} id={id} textValue={t(id === "all" ? "workspace.debug.all" : `workspace.debug.kinds.${id}`)}>
        {t(id === "all" ? "workspace.debug.all" : `workspace.debug.kinds.${id}`)}<ListBox.ItemIndicator />
      </ListBox.Item>)}</ListBox></Select.Popover>
    </Select>
    <Select aria-label={t("workspace.debug.source")} value={trace.source || ":all"} onChange={key => { if (key !== null) trace.setSource(key === ":all" ? "" : String(key)); }}>
      <Select.Trigger><Select.Value>{trace.source ? sourceLabel(trace.source) : t("workspace.debug.allSources")}</Select.Value><Select.Indicator /></Select.Trigger>
      <Select.Popover><ListBox>{[":all", ...sources].map(id => <ListBox.Item key={id} id={id} textValue={id === ":all" ? t("workspace.debug.allSources") : sourceLabel(id)}>
        {id === ":all" ? t("workspace.debug.allSources") : sourceLabel(id)}<ListBox.ItemIndicator />
      </ListBox.Item>)}</ListBox></Select.Popover>
    </Select>
    <SearchField value={query} onChange={onQuery} aria-label={t("workspace.debug.filter")}><SearchField.Group><SearchField.SearchIcon />
      <SearchField.Input placeholder={t("workspace.debug.filter")} /><SearchField.ClearButton />
    </SearchField.Group></SearchField>
  </div>;
}

export function TraceFooter({ trace, count }: { trace: TraceState; count: number }) {
  const { t } = useTranslation();
  return <footer className="trace-footer"><span>{t("workspace.debug.count", { count, total: trace.info?.count ?? 0 })} · {t(trace.info?.running ? "workspace.debug.recording" : "workspace.debug.paused")}</span>
    <div><TraceAction label={t("workspace.debug.newest")} disabled={!trace.canNewer || trace.busy} onPress={trace.newest}><ChevronsUp size={14} /></TraceAction>
      <Button size="sm" variant="ghost" isDisabled={!trace.canNewer || trace.busy} onPress={trace.newer}><ArrowUp size={12} />{t("workspace.debug.newer")}</Button>
      <Button size="sm" variant="ghost" isDisabled={!trace.page?.before || trace.busy} onPress={trace.older}><ArrowDown size={12} />{t("workspace.loadOlder")}</Button>
    </div>
  </footer>;
}
