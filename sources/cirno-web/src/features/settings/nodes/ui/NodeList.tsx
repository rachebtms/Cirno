import { Button, Card } from "@heroui/react";
import { Pencil, Terminal, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Hint } from "@/ui/feedback/Hint";
import type { NodesController } from "../model/useNodes";

export function NodeList({ nodes }: { nodes: NodesController }) {
  const { t } = useTranslation();
  return <Card className="node-list"><ul>{nodes.nodes.map(node => <li key={node.id}>
    <div className="node-identity"><strong>{node.name}</strong><span>{node.username}@{node.host}:{node.port}</span>{node.agent_visible !== undefined && <small>{t(node.agent_visible ? "workspace.agentVisible" : "workspace.agentHidden")}</small>}</div>
    <div className="node-actions">
      <Button size="sm" variant="secondary" isDisabled={nodes.busy} onPress={() => { void nodes.test(node); }}>{t("features.test")}</Button>
      <Hint content={t("features.executeCommand")}><Button isIconOnly size="sm" variant="ghost" aria-label={t("features.executeCommand")} isDisabled={nodes.busy} onPress={() => nodes.startCommand(node)}><Terminal size={17} /></Button></Hint>
      <Hint content={t("features.edit")}><Button isIconOnly size="sm" variant="ghost" aria-label={t("features.edit")} isDisabled={nodes.busy} onPress={() => nodes.edit(node)}><Pencil size={17} /></Button></Hint>
      <Hint content={t("features.removeNode")}><Button isIconOnly size="sm" variant="ghost" aria-label={t("features.removeNode")} isDisabled={nodes.busy} onPress={() => { void nodes.remove(node); }}><Trash2 size={17} /></Button></Hint>
    </div>
  </li>)}</ul></Card>;
}
