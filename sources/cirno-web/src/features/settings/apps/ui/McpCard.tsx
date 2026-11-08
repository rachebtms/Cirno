import { Button, Card, Chip } from "@heroui/react";
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import { ToggleField } from "@/ui/fields/ToggleField";
import { McpManagementDialog, type McpManagementTab } from "../../mcp/McpManagementDialog";
import type { AppsCatalogProps } from "../model/contracts";
import { mcpPresetStatusLabel } from "../model/status";
import { CatalogLogo } from "./CatalogLogo";
import { McpAuthorization } from "./McpAuthorization";

export function McpCard({ preset, options }: { preset: McpPresetInfo; options: AppsCatalogProps }) {
  const { t } = useTranslation();
  const statusId = useId();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<McpManagementTab>("overview");
  useEffect(() => {
    if (options.setupName !== preset.name) return;
    setTab("connection"); setOpen(true); options.onSetupOpened?.();
  }, [options.setupName, options.onSetupOpened, preset.name]);
  const busy = options.mcpActionKey?.endsWith(`:${preset.name}`) ?? false;
  const flow = options.mcpOAuthFlow?.name === preset.name ? options.mcpOAuthFlow : null;
  const configured = preset.installed && preset.configured;
  const toggleable = preset.enabled !== undefined;
  const failed = !toggleable && preset.installed && preset.runtime_status === "failed";
  const connecting = Boolean(flow) || !toggleable && configured && preset.runtime_status === "connecting";
  const ready = preset.enabled ?? configured;
  const values = options.mcpFieldValues[preset.name] ?? {};
  const description = t(`settings.mcp.presetDescriptions.${preset.name}`, { defaultValue: preset.description || preset.note || preset.name });
  const status = failed ? t("settings.mcp.connectionFailed").replace(/[.!。！]+$/u, "") : connecting ? t("settings.mcp.connectingLabel") : toggleable ? t(preset.enabled ? "settings.cirnoFeatures.enabled" : "settings.values.disabled")
    : preset.runtime_status === "connected" ? t("connection.open") : mcpPresetStatusLabel(preset.status, (key, fallback) => t(key, { defaultValue: fallback }));
  const manage = (next: McpManagementTab = "overview") => { setTab(next); setOpen(true); };
  const connect = () => {
    const needsInput = preset.required_fields.some(field => field.required && !field.configured);
    if (preset.transport !== "stdio" || needsInput || preset.installed && !preset.configured && preset.required_fields.length) manage("connection");
    else if (preset.auth === "oauth") options.onMcpOAuthConnect(preset.name);
    else options.onMcpAction("enable", preset.name, values);
  };
  const logo = <CatalogLogo name={preset.display_name} logo={preset.logo_url} color={preset.brand_color} show={options.showBrandLogos} />;
  return <Card role="article" aria-label={preset.display_name} className="catalog-card"><Card.Content>
    <div className="catalog-row">
      <div className="catalog-open">{logo}<div className="catalog-identity"><h3><Button variant="ghost" className="catalog-title-button" aria-label={preset.display_name} aria-describedby={connecting ? statusId : undefined} onPress={() => manage()}>{preset.display_name}</Button></h3><p>{description}</p></div></div>
      <Chip id={statusId} size="sm" variant="soft" color={failed ? "warning" : ready ? "success" : "default"}>{status}</Chip>
      <div className="catalog-actions">{flow ? <Button variant="danger-soft" onPress={options.onMcpOAuthCancel}>{t("settings.actions.cancel")}</Button>
        : connecting && configured ? <Button variant="danger-soft" isPending={busy} onPress={() => options.onMcpAction("remove", preset.name)}>{t("settings.mcp.remove")}</Button>
        : failed ? <Button variant="secondary" isDisabled={busy} aria-label={t("settings.mcp.manageTitle", { name: preset.display_name })} onPress={() => manage("connection")}>{t("settings.mcp.fixConnection")}</Button>
        : toggleable ? <ToggleField label={preset.display_name} selected={Boolean(preset.enabled)} disabled={busy} onChange={selected => options.onMcpAction(selected ? "enable" : "disable", preset.name, values)} />
        : ready ? <Button variant="secondary" isDisabled={busy} aria-label={t("settings.mcp.manageTitle", { name: preset.display_name })} onPress={() => manage()}>{t("settings.mcp.manage")}</Button>
        : <Button variant="secondary" isPending={busy} isDisabled={!preset.install_supported || busy || Boolean(options.mcpActionKey?.startsWith("oauth:"))}
          aria-label={t("settings.mcp.connectTitle", { name: preset.display_name })} onPress={connect}>{t(preset.install_supported ? "settings.mcp.setup" : "settings.mcp.comingSoon")}</Button>}
      </div>
    </div>
    {failed && <p role="alert" className="catalog-error">{preset.error || t("settings.mcp.connectionFailed")}</p>}
    {flow && <McpAuthorization options={options} />}
    {open && <McpManagementDialog preset={preset} values={values} actionKey={options.mcpActionKey} statusLabel={status}
      statusTone={failed ? "warning" : configured ? "success" : "neutral"} tab={tab} icon={logo} onTabChange={setTab} onOpenChange={setOpen}
      onFieldChange={options.onMcpFieldChange} onAction={options.onMcpAction} onOAuthConnect={options.onMcpOAuthConnect} onToolsChange={options.onMcpToolsChange}
      onConfigureProxy={options.onConfigureProxy} configEditor={options.mcpConfigEditor} error={options.mcpError} />}
  </Card.Content></Card>;
}
