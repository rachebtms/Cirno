import { Alert, Button, Checkbox, CheckboxGroup, Label, SearchField, Spinner } from "@heroui/react";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { McpManagementDialogProps } from "../model/contracts";
import type { McpManagementModel } from "../model/useMcpManagement";
import { displayToolName } from "../model/tools";

export function ToolsPanel({ options, model }: { options: McpManagementDialogProps; model: McpManagementModel }) {
  const { t } = useTranslation();
  const { preset } = options;
  if (!model.toolNames.length) return <div className="mcp-fields">
    {model.testBusy ? <div role="status" aria-busy="true" aria-label={t("settings.mcp.loadingTools")} className="mcp-loading"><Spinner size="sm" />{t("settings.mcp.loadingTools")}</div>
      : <><Alert status={preset.error ? "danger" : "default"} role={preset.error ? "alert" : "status"}><Alert.Description>{preset.error || t("settings.mcp.noToolsAvailable")}</Alert.Description></Alert>
        <Button variant="secondary" onPress={model.connected ? model.refreshTools : () => options.onTabChange("connection")}><RefreshCw size={16} />{t(model.connected ? "settings.mcp.reloadTools" : "settings.mcp.setup")}</Button></>}
  </div>;
  return <div className="mcp-fields">
    {preset.error && <Alert status="danger" role="alert"><Alert.Description>{preset.error}</Alert.Description></Alert>}
    <div className="mcp-tools-toolbar">
      <SearchField value={model.query} onChange={model.setQuery} aria-label={t("settings.mcp.searchTools")}><SearchField.Group><SearchField.SearchIcon /><SearchField.Input placeholder={t("settings.mcp.searchToolsPlaceholder")} /><SearchField.ClearButton /></SearchField.Group></SearchField>
      <span className="mcp-description">{t("settings.mcp.selectedCount", { count: model.selectedCount })}</span>
      <Button variant="ghost" isDisabled={model.busy} onPress={model.selectAll}>{t("settings.mcp.allTools")}</Button>
      <Button variant="ghost" isDisabled={model.busy} onPress={model.clear}>{t("settings.mcp.noTools")}</Button>
    </div>
    <CheckboxGroup aria-label={t("settings.mcp.toolScope")} value={model.selected} onChange={model.changeTools} isDisabled={model.busy} className="mcp-tool-list">
      {model.filteredTools.map(name => <Checkbox key={name} value={name} className="mcp-tool-row"><Checkbox.Content><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><Label><code>{displayToolName(name, preset.name)}</code></Label></Checkbox.Content></Checkbox>)}
    </CheckboxGroup>
    {!model.filteredTools.length && <p className="mcp-description">{t("settings.mcp.noMatchingTools")}</p>}
  </div>;
}
