import { Card, Chip, Link } from "@heroui/react";
import { ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { McpManagementDialogProps } from "../model/contracts";
import type { McpManagementModel } from "../model/useMcpManagement";
import { displayToolName, formatTransport } from "../model/tools";

export function OverviewPanel({ options, model, description }: { options: McpManagementDialogProps; model: McpManagementModel; description: string }) {
  const { t } = useTranslation();
  const { preset, statusLabel } = options;
  const count = preset.tool_count ?? model.toolNames.length;
  return <div className="mcp-fields">
    <Card><Card.Content className="mcp-fields"><h3>{t("settings.mcp.about")}</h3><p className="mcp-description">{description}</p>
      {preset.docs_url && <Link href={preset.docs_url} target="_blank" rel="noreferrer">{t("settings.mcp.openDocs")}<ExternalLink size={15} /></Link>}
    </Card.Content></Card>
    <dl className="mcp-metrics">{[
      [t("settings.mcp.statusLabel"), statusLabel], [t("settings.mcp.transportLabel"), formatTransport(preset.transport)],
      ...(count ? [[t("settings.mcp.toolScope"), `${model.selectedCount} / ${count}`]] : []),
    ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    {model.toolNames.length > 0 && <div className="mcp-tool-preview">{model.toolNames.slice(0, 4).map(name => <Chip key={name} variant="soft"><code>{displayToolName(name, preset.name)}</code></Chip>)}
      {count > 4 && <Chip variant="soft">+{count - 4}</Chip>}
    </div>}
  </div>;
}
