import { useSourceLabel } from "@/features/conversations/catalog/useSourceLabel";
import { Table } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { TraceEvent } from "./contracts";
import { eventGroup } from "./contracts";

export function TraceTable({ events, selected, select }: {
  events: TraceEvent[]; selected: number | undefined; select: (event: TraceEvent) => void;
}) {
  const { t } = useTranslation();
  const sourceLabel = useSourceLabel();
  return <Table variant="secondary" className="trace-table-root"><Table.Content className="trace-table" aria-label={t("workspace.debug.events")}
    selectionMode="single" selectionBehavior="replace" disallowEmptySelection selectedKeys={selected === undefined ? [] : [selected]}
    onSelectionChange={keys => { const id = keys === "all" ? undefined : keys.values().next().value; const event = events.find(event => event.id === id); if (event) select(event); }}>
    <Table.Header>{["time", "type", "summary", "status", "source", "turn", "size"].map(id => <Table.Column key={id} id={id} isRowHeader={id === "summary"}>{t(`workspace.debug.${id}`)}</Table.Column>)}</Table.Header>
    <Table.Body items={events}>{event => <Table.Row id={event.id} textValue={event.summary || event.kind} data-event-kind={event.kind}>
      <Table.Cell className="trace-time"><span title={new Date(event.created_ms).toLocaleString()}>{event.created_ms ? new Date(event.created_ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, fractionalSecondDigits: 3 }) : "—"}</span></Table.Cell>
      <Table.Cell><span className={`trace-kind trace-kind-${eventGroup(event.kind)}`}>{t(`workspace.debug.kinds.${eventGroup(event.kind)}`)}</span></Table.Cell>
      <Table.Cell className="trace-summary"><span title={event.summary}>{event.summary || event.kind}</span></Table.Cell>
      <Table.Cell><span title={event.status}>{event.status || "—"}</span></Table.Cell>
      <Table.Cell><span title={event.session_key}>{sourceLabel(event.session_key)}</span></Table.Cell>
      <Table.Cell><span title={event.turn_id ?? ""}>{event.turn_id?.split(":").at(-1)?.slice(-10) ?? "—"}</span></Table.Cell>
      <Table.Cell className="trace-size">{event.bytes == null ? "—" : `${(event.bytes / 1024).toFixed(1)} kB`}</Table.Cell>
    </Table.Row>}</Table.Body>
  </Table.Content></Table>;
}
