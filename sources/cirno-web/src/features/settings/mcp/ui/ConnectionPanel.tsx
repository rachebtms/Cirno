import { Alert, Button, Card, Description, Input, Label, Link, TextField } from "@heroui/react";
import { ExternalLink, RefreshCw, SquarePen, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ProxySettingsControl } from "../../shared/ProxySettingsControl";
import { SettingsTextEditor } from "../../shared/SettingsTextEditor";
import type { McpManagementDialogProps } from "../model/contracts";
import type { McpManagementModel } from "../model/useMcpManagement";
import { formatTransport } from "../model/tools";

export function ConnectionPanel({ options, model }: { options: McpManagementDialogProps; model: McpManagementModel }) {
  const { t } = useTranslation();
  const { preset, configEditor } = options;
  const connectLabel = t(model.connected ? "settings.mcp.reconnect" : "settings.mcp.setup");
  return <div className="mcp-fields">
    <Card><Card.Content className="mcp-fields">
      {preset.connection_summary && <div><p className="mcp-description">{t(preset.transport === "stdio" ? "settings.mcp.command" : "settings.mcp.endpointLabel")}</p><code className="mcp-endpoint">{preset.connection_summary}</code></div>}
      <div className="mcp-connection-meta"><span>{formatTransport(preset.transport)}</span><span>{preset.auth === "oauth" ? "OAuth" : t(preset.required_fields.length ? "settings.mcp.credentials" : "settings.mcp.none")}</span>
        {preset.docs_url && <Link href={preset.docs_url} target="_blank" rel="noreferrer">{t("settings.mcp.openDocs")}<ExternalLink size={15} /></Link>}
      </div>
    </Card.Content></Card>
    {preset.error && <Alert status="danger" role="alert"><Alert.Description>{preset.error}</Alert.Description></Alert>}
    {preset.source === "custom" && configEditor && <SettingsTextEditor title={t("settings.mcp.editConfig")} value="" json disabled={model.busy}
      loadValue={() => configEditor.load(preset.name)} onSave={config => configEditor.save(preset.name, config)}
      trigger={<Button variant="secondary" isDisabled={model.busy}><SquarePen size={16} />{t("settings.mcp.editConfig")}</Button>} />}
    {preset.transport !== "stdio" && <ProxySettingsControl checked={model.connectionValues.use_proxy === "true"} disabled={model.busy}
      onChange={checked => options.onFieldChange(preset.name, "use_proxy", String(checked))} onConfigure={options.onConfigureProxy} />}
    {preset.required_fields.map(field => <TextField key={field.name} value={options.values[field.name] ?? ""} isDisabled={model.busy}
      onChange={value => options.onFieldChange(preset.name, field.name, value)}>
      <Label>{field.label}</Label>{field.configured && <Description>{t("settings.mcp.configured")}</Description>}
      <Input type={field.secret ? "password" : "text"} autoComplete={field.secret ? "new-password" : "off"}
        placeholder={field.configured ? t("settings.mcp.keepExisting") : field.placeholder} />
    </TextField>)}
    <div className="mcp-connection-actions">
      {preset.installed && preset.enabled === undefined && <Button variant="danger-soft" isDisabled={model.busy} onPress={model.remove}><Trash2 size={16} />{t("settings.mcp.dangerZone")}</Button>}
      {preset.install_supported && <Button isDisabled={model.busy || !model.requiredComplete} onPress={model.connect}><RefreshCw size={16} />{connectLabel}</Button>}
    </div>
  </div>;
}
