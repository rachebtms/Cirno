import { Button, Spinner, Tabs } from "@heroui/react";
import { X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { TraceDetail, TraceEvent } from "./contracts";

export function TraceInspector({ event, detail, busy, close, more }: {
  event: TraceEvent; detail: TraceDetail | null; busy: boolean; close: () => void; more: () => void;
}) {
  const { t } = useTranslation();
  const [section, setSection] = useState(event.kind === "request" ? "messages" : "raw");
  const sections = event.kind === "request" ? ["messages", "response", "tools", "raw"] : ["raw"];
  const value = section === "raw" ? detail?.event ?? detail : detail?.[section as "messages" | "response" | "tools"];
  return <section className="trace-inspector" aria-label={t("workspace.debug.inspector")}>
    <header className="trace-inspector-head"><span title={String(event.id)}>{event.session_key} / #{event.id}</span>
      <Button isIconOnly size="sm" variant="ghost" onPress={close} aria-label={t("common.close")}><X size={14} /></Button>
    </header>
    <Tabs className="trace-inspector-tabs" selectedKey={section} onSelectionChange={key => setSection(String(key))}>
      <Tabs.ListContainer><Tabs.List aria-label={t("workspace.debug.inspector")}>{sections.map(id => <Tabs.Tab key={id} id={id}>{t(`workspace.debug.${id}`)}<Tabs.Indicator /></Tabs.Tab>)}</Tabs.List></Tabs.ListContainer>
      <Tabs.Panel id={section} className="trace-inspector-body" aria-busy={busy}>
        {busy && !detail ? <Spinner size="sm" aria-label={t("settings.status.loading")} /> : <pre>{value == null ? "—" : JSON.stringify(value, null, 2)}</pre>}
        {section === "messages" && detail?.messages && detail.messages.length < (detail.total ?? 0) &&
          <Button size="sm" variant="secondary" isDisabled={busy} onPress={more}>{t("workspace.loadMore")} ({detail.messages.length}/{detail.total})</Button>}
      </Tabs.Panel>
    </Tabs>
  </section>;
}
