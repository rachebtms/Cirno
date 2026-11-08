import { Alert, Button, Chip, Modal, Tabs } from "@heroui/react";
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { McpManagementDialogProps, McpManagementTab } from "./model/contracts";
import { useMcpManagement } from "./model/useMcpManagement";
import { ConnectionPanel } from "./ui/ConnectionPanel";
import { OverviewPanel } from "./ui/OverviewPanel";
import { ToolsPanel } from "./ui/ToolsPanel";
import "./mcp.css";
export type { McpConfigEditor, McpManagementTab } from "./model/contracts";

export function McpManagementDialog(options: McpManagementDialogProps) {
  const { t } = useTranslation();
  const model = useMcpManagement(options);
  const { preset, tab } = options;
  const description = t(`settings.mcp.presetDescriptions.${preset.name}`, { defaultValue: preset.description || preset.note || preset.name });
  const sections: Array<{ id: McpManagementTab; label: string }> = [
    { id: "overview", label: t("settings.mcp.overviewTab") }, { id: "tools", label: t("settings.mcp.toolScope") }, { id: "connection", label: t("settings.mcp.connectionTab") },
  ];
  return <Modal.Backdrop isOpen onOpenChange={options.onOpenChange} ><Modal.Container size="lg"><Modal.Dialog className="mcp-management-dialog">
      <Modal.Header className="mcp-management-heading">{options.icon}<Modal.Heading>{preset.display_name}</Modal.Heading>
        <Chip variant="soft" color={options.statusTone === "success" ? "success" : options.statusTone === "warning" ? "warning" : "default"}>{options.statusLabel}</Chip><Modal.CloseTrigger />
      </Modal.Header>
      {options.error && <Alert status="danger" role="alert"><Alert.Description>{options.error}</Alert.Description></Alert>}
      <Tabs selectedKey={tab} onSelectionChange={key => options.onTabChange(key as McpManagementTab)} className="mcp-management-tabs">
        <Tabs.ListContainer><Tabs.List aria-label={t("settings.mcp.manageTabs")}>{sections.map(section => <Tabs.Tab key={section.id} id={section.id}>{section.label}<Tabs.Indicator /></Tabs.Tab>)}</Tabs.List></Tabs.ListContainer>
        <Tabs.Panel id="overview"><OverviewPanel options={options} model={model} description={description} /></Tabs.Panel>
        <Tabs.Panel id="tools"><ToolsPanel options={options} model={model} /></Tabs.Panel>
        <Tabs.Panel id="connection"><ConnectionPanel options={options} model={model} /></Tabs.Panel>
      </Tabs>
      {tab === "tools" && model.toolsDirty && <Modal.Footer><Button isPending={model.toolsBusy} isDisabled={model.busy || !model.toolNames.length} onPress={model.applyTools}><Check size={16} />{t("settings.mcp.applyChanges")}</Button></Modal.Footer>}
      {tab === "connection" && preset.installed && model.proxyDirty && <Modal.Footer><Button isDisabled={model.busy} onPress={model.applyProxy}>{t("settings.mcp.applyChanges")}</Button></Modal.Footer>}
    </Modal.Dialog></Modal.Container></Modal.Backdrop>;
}
