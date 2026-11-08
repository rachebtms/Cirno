import { Button, Spinner, Tabs } from "@heroui/react";
import { Check, Copy, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { copyTextToClipboard } from "@/lib/clipboard";
import type { TraceDetail, TraceEvent } from "./contracts";

export function TraceInspector({ event, detail, busy, close, more }: {
  event: TraceEvent; detail: TraceDetail | null; busy: boolean; close: () => void; more: () => void;
}) {
  const { t } = useTranslation();
  const [copiedText, setCopiedText] = useState<string | null>(null);
  const [copyError, setCopyError] = useState(false);
  const [section, setSection] = useState(event.kind === "request" ? "messages" : "raw");
  const sections = event.kind === "request" ? ["messages", "response", "tools", "raw"] : ["raw"];
  const value = section === "raw" ? detail?.event ?? detail : detail?.[section as "messages" | "response" | "tools"];
  const text = value == null ? "—" : JSON.stringify(value, null, 2);
  const copied = copiedText === text;
  const copy = async () => {
    const ok = await copyTextToClipboard(text);
    setCopiedText(ok ? text : null); setCopyError(!ok);
  };
  return <section className="trace-inspector" aria-label={t("workspace.debug.inspector")}>
    <header className="trace-inspector-head"><span title={String(event.id)}>{event.session_key} / #{event.id}</span>
      <Button isIconOnly size="sm" variant="ghost" isDisabled={busy || value == null} onPress={() => void copy()}
        aria-label={t(copied ? "workspace.debug.copied" : "workspace.debug.copy")}>
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </Button>
      <Button isIconOnly size="sm" variant="ghost" onPress={close} aria-label={t("common.close")}><X size={14} /></Button>
    </header>
    {copyError && <p role="alert" className="trace-error">{t("workspace.debug.copyFailed")}</p>}
    <Tabs className="trace-inspector-tabs" selectedKey={section} onSelectionChange={key => { setSection(String(key)); setCopiedText(null); setCopyError(false); }}>
      <Tabs.ListContainer><Tabs.List aria-label={t("workspace.debug.inspector")}>{sections.map(id => <Tabs.Tab key={id} id={id}>{t(`workspace.debug.${id}`)}<Tabs.Indicator /></Tabs.Tab>)}</Tabs.List></Tabs.ListContainer>
      <Tabs.Panel id={section} className="trace-inspector-body" aria-busy={busy}>
        {busy && !detail ? <Spinner size="sm" aria-label={t("settings.status.loading")} /> : <pre>{text}</pre>}
        {section === "messages" && detail?.messages && detail.messages.length < (detail.total ?? 0) &&
          <Button size="sm" variant="secondary" isDisabled={busy} onPress={more}>{t("workspace.loadMore")} ({detail.messages.length}/{detail.total})</Button>}
      </Tabs.Panel>
    </Tabs>
  </section>;
}
