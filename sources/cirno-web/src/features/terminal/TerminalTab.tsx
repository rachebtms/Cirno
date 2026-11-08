import { Alert, Button, Form, ListBox, Select } from "@heroui/react";
import { useMemo, useState } from "react";
import { CircleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CirnoClient } from "@/lib/cirno-client";
import { usePreferences } from "@/hooks/usePreferences";
import { useTheme } from "@/hooks/useTheme";
import { useTerminalHosts } from "./model/useTerminalHosts";
import { useTerminalSession } from "./model/useTerminalSession";
import "./terminal.css";

export function TerminalTab({ client, cwd, terminalKey, active, onCloseReady }: {
  client: CirnoClient; cwd?: string; terminalKey: string; active: boolean; onCloseReady: (close: () => Promise<void>) => void;
}) {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const preferences = usePreferences();
  const paletteRevision = useMemo(() => ({ theme, id: preferences.themeId, custom: preferences.customThemes }), [theme, preferences.themeId, preferences.customThemes]);
  const hosts = useTerminalHosts(client);
  const [nodeId, setNodeId] = useState("local");
  const session = useTerminalSession({ client, cwd, nodeId, terminalKey, active, onCloseReady, paletteRevision,
    exitedText: code => t("workspace.terminalExited", { code }) });
  const busy = session.phase === "connecting";
  const choices = [{ id: "local", name: t("workspace.localServer") }, ...hosts.nodes];
  return <section className="terminal-screen" aria-label={t("workspace.terminal")}>
    <Form className="terminal-toolbar" onSubmit={event => { event.preventDefault(); void session.connect(); }}>
      <Select aria-label={t("workspace.terminalHost")} value={nodeId} isDisabled={session.started || busy} onChange={key => { if (key !== null) setNodeId(String(key)); }}>
        <Select.Trigger><Select.Value>{choices.find(row => row.id === nodeId)?.name ?? nodeId}</Select.Value><Select.Indicator /></Select.Trigger>
        <Select.Popover><ListBox items={choices}>{node => <ListBox.Item id={node.id} textValue={node.name}>{node.name}<ListBox.ItemIndicator /></ListBox.Item>}</ListBox></Select.Popover>
      </Select>
      <span className="terminal-directory" title={cwd}>{cwd}</span>
      {session.phase !== "connected" && <Button type="submit" size="sm" isPending={busy}>{t(session.phase === "failed" ? "common.retry" : "workspace.connect")}</Button>}
    </Form>
    {hosts.error && <Alert status="danger" role="alert"><Alert.Indicator><CircleAlert /></Alert.Indicator><Alert.Content><Alert.Description>{hosts.error}</Alert.Description></Alert.Content><Button variant="ghost" size="sm" onPress={hosts.retry}>{t("common.retry")}</Button></Alert>}
    {session.errors.map(error => <Alert status="danger" role="alert" key={error}><Alert.Indicator><CircleAlert /></Alert.Indicator><Alert.Content><Alert.Description>{error}</Alert.Description></Alert.Content></Alert>)}
    {!session.started && <p className="terminal-hint">{t("workspace.terminalHint")}</p>}
    <div ref={session.host} className="terminal-canvas" />
  </section>;
}
