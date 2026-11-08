import { Accordion, Alert, Button, Card, Description, Form, Input, Label, ListBox, Select, TextArea, TextField } from "@heroui/react";
import { Download, Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ProxySettingsControl } from "../../shared/ProxySettingsControl";
import type { AppsCatalogProps, CustomMcpForm } from "../model/contracts";

export function CustomMcpPanel({ options }: { options: AppsCatalogProps }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"custom" | "import" | null>(null);
  const [error, setError] = useState("");
  const form = options.customMcpForm;
  const customBusy = options.mcpActionKey?.startsWith("custom:") ?? false;
  const importBusy = options.mcpActionKey === "import" || options.mcpActionKey === "import-cursor";
  const busy = customBusy || importBusy;
  const remote = form.transport !== "stdio";
  const canSave = Boolean(form.name.trim() && (remote ? form.url.trim() : form.command.trim()));
  const update = <K extends keyof CustomMcpForm>(key: K, value: CustomMcpForm[K]) => options.onCustomMcpFormChange(current => ({ ...current, [key]: value }));
  const format = () => {
    try { options.onMcpConfigImportChange(JSON.stringify(JSON.parse(options.mcpConfigImport), null, 2)); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
  };
  return <Card><Card.Header className="catalog-custom-heading"><div><Card.Title>{t("settings.mcp.moreOptions")}</Card.Title><p className="catalog-description">{t("settings.mcp.moreOptionsSubtitle")}</p></div>
    <div className="catalog-actions"><Button variant={mode === "custom" ? "primary" : "secondary"} isDisabled={busy} onPress={() => setMode(current => current === "custom" ? null : "custom")}><Plus size={16} />{t("settings.mcp.customAction")}</Button>
      <Button variant={mode === "import" ? "primary" : "secondary"} isDisabled={busy} onPress={() => setMode(current => current === "import" ? null : "import")}><Download size={16} />{t("settings.mcp.importAction")}</Button></div>
  </Card.Header>
    {mode === "custom" && <Card.Content><Form className="catalog-fields" onSubmit={event => { event.preventDefault(); options.onSaveCustomMcp(); }}>
      <div className="catalog-columns">
        <TextField value={form.name} onChange={value => update("name", value)} isRequired isDisabled={busy}><Label>{t("settings.mcp.serverName")}</Label><Input placeholder="docs" /></TextField>
        <Select value={form.transport} onChange={value => update("transport", value as CustomMcpForm["transport"])} isDisabled={busy}>
          <Label>{t("settings.mcp.transport")}</Label><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox>
            {([{ id: "stdio", name: "stdio" }, { id: "streamableHttp", name: "HTTP" }, { id: "sse", name: "SSE" }]).map(item => <ListBox.Item key={item.id} id={item.id} textValue={item.name}>{item.name}<ListBox.ItemIndicator /></ListBox.Item>)}
          </ListBox></Select.Popover>
        </Select>
      </div>
      <TextField value={remote ? form.url : form.command} onChange={value => remote ? update("url", value) : update("command", value)} isRequired isDisabled={busy}>
        <Label>{t(remote ? "settings.mcp.serverUrl" : "settings.mcp.command")}</Label><Input placeholder={remote ? "https://example.com/mcp" : "npx"} autoComplete="off" spellCheck={false} />
      </TextField>
      {remote && <>
        <Select value={form.auth} onChange={value => update("auth", value as CustomMcpForm["auth"])} isDisabled={busy}>
          <Label>{t("settings.mcp.authentication")}</Label><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox>
            {([{ id: "none", name: t("settings.mcp.authNone") }, { id: "oauth", name: "OAuth" }, { id: "headers", name: t("settings.mcp.authHeaders") }]).map(item => <ListBox.Item key={item.id} id={item.id} textValue={item.name}>{item.name}<ListBox.ItemIndicator /></ListBox.Item>)}
          </ListBox></Select.Popover>
        </Select>
        {form.auth === "oauth" && <p className="catalog-description">{t("settings.mcp.oauthAfterSave")}</p>}
        <ProxySettingsControl checked={form.useProxy} disabled={busy} onChange={value => update("useProxy", value)} onConfigure={options.onConfigureProxy} />
        {form.auth === "headers" && <TextField value={form.headers} onChange={value => update("headers", value)} isDisabled={busy}><Label>{t("settings.mcp.headers")}</Label><Description>{t("settings.mcp.headersHelp")}</Description><TextArea spellCheck={false} rows={3} className="catalog-json" placeholder={'{\n  "Authorization": "Bearer ..."\n}'} /></TextField>}
      </>}
      <Accordion><Accordion.Item id="advanced"><Accordion.Heading><Accordion.Trigger>{t("settings.mcp.advancedOptions")}<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body className="catalog-fields">
        {!remote && <TextField value={form.args} onChange={value => update("args", value)} isDisabled={busy}><Label>{t("settings.mcp.args")}</Label><TextArea spellCheck={false} rows={3} className="catalog-json" placeholder={'[\n  "-y",\n  "docs-mcp"\n]'} /></TextField>}
        <TextField value={form.env} onChange={value => update("env", value)} isDisabled={busy}><Label>{t("settings.mcp.env")}</Label><TextArea spellCheck={false} rows={3} className="catalog-json" placeholder={'{\n  "API_KEY": "..."\n}'} /></TextField>
        <TextField value={form.toolTimeout} onChange={value => update("toolTimeout", value)} isDisabled={busy}><Label>{t("settings.mcp.timeout")}</Label><Input inputMode="numeric" /></TextField>
      </Accordion.Body></Accordion.Panel></Accordion.Item></Accordion>
      <div className="catalog-actions"><Button type="submit" isPending={customBusy} isDisabled={busy || !canSave}>{t("settings.mcp.saveCustom")}</Button></div>
    </Form></Card.Content>}
    {mode === "import" && <Card.Content><Form aria-label={t("settings.mcp.configImport")} validationBehavior="aria" className="catalog-fields" onSubmit={event => { event.preventDefault(); options.onImportMcpConfig(); }}>
      <TextField value={options.mcpConfigImport} isDisabled={busy} isInvalid={Boolean(error)} onChange={value => { options.onMcpConfigImportChange(value); setError(""); }}>
        <Label>{t("settings.mcp.configImport")}</Label><TextArea rows={8} className="catalog-json" spellCheck={false} placeholder={JSON.stringify({ mcpServers: { docs: { command: "npx", args: ["-y", "docs-mcp"] } } }, null, 2)} />
      </TextField>
      {error && <Alert status="danger" role="alert"><Alert.Description>{error}</Alert.Description></Alert>}
      <div className="catalog-actions"><Button variant="ghost" isDisabled={busy || !options.mcpConfigImport.trim()} onPress={format}>{t("settings.actions.formatJson")}</Button>
        <Button type="submit" isPending={importBusy} isDisabled={busy || !options.mcpConfigImport.trim()}>{t("settings.mcp.importConfig")}</Button></div>
    </Form></Card.Content>}
  </Card>;
}
