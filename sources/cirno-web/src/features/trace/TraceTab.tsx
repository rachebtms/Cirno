import type { CirnoClient } from "@/lib/cirno-client";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useTrace } from "./useTrace";
import { TraceTable } from "./TraceTable";
import { TraceInspector } from "./TraceInspector";
import { TraceFooter, TraceToolbar } from "./TraceControls";
import "./trace.css";

export function TraceTab({ client, recordingId, active, onCloseReady }: {
  client: CirnoClient; recordingId: string; active: boolean; onCloseReady: (close: () => Promise<void>) => void;
}) {
  const { t } = useTranslation();
  const trace = useTrace(client, recordingId, active, onCloseReady);
  const [query, setQuery] = useState("");
  const events = useMemo(() => trace.page?.events.filter(event =>
    [event.summary, event.status, event.kind, event.session_key, event.turn_id, event.id].join(" ").toLocaleLowerCase().includes(query.toLocaleLowerCase())
  ) ?? [], [trace.page, query]);
  return <div className="trace-console">
    <TraceToolbar trace={trace} query={query} onQuery={setQuery} />
    {trace.error && <div role="alert" className="trace-error">{trace.error}</div>}
    {trace.info?.reason && <div role="status" className="trace-error">{t(`workspace.debug.${trace.info.reason}`)}</div>}
    <div className={`trace-content ${trace.selected ? "trace-has-selection" : ""}`}>
      <div className="trace-event-scroll" aria-busy={trace.busy}>
        <TraceTable events={events} selected={trace.selected?.id} select={trace.setSelected} />
        {!events.length && <p role="status" className="trace-empty">{t(!trace.info && !trace.error || trace.busy ? "settings.status.loading" : trace.info?.running ? "workspace.debug.waiting" : "workspace.debug.noEvents")}</p>}
      </div>
      {trace.selected && <TraceInspector key={trace.selected.id} event={trace.selected} detail={trace.detail} busy={trace.detailBusy} close={() => trace.setSelected(null)} more={trace.moreDetail} />}
    </div>
    <TraceFooter trace={trace} count={events.length} />
  </div>;
}
