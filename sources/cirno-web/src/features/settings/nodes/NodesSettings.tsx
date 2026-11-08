import { Alert, Button, Spinner } from "@heroui/react";
import { CircleAlert, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CirnoClient } from "@/lib/cirno-client";
import { useNodes } from "./model/useNodes";
import { NodeEditor } from "./ui/NodeEditor";
import { NodeCommand } from "./ui/NodeCommand";
import { NodeList } from "./ui/NodeList";
import { NodeJobs } from "./ui/NodeJobs";
import "./nodes.css";

export function NodesSettings({ client }: { client: CirnoClient }) {
  const { t } = useTranslation();
  const nodes = useNodes(client);
  return <section className="nodes-settings" aria-label="Nodes">
    <header className="node-toolbar"><Button size="sm" isDisabled={nodes.busy} onPress={() => nodes.edit()}><Plus size={16} />{t("features.addNode")}</Button></header>
    <p className="node-help">{t("features.nodesDescription")}</p>
    {nodes.listError && <Alert status="danger" role="alert"><Alert.Indicator><CircleAlert /></Alert.Indicator><Alert.Content><Alert.Description>{nodes.listError}</Alert.Description></Alert.Content>
      <Button size="sm" variant="ghost" isDisabled={nodes.loading} onPress={() => { void nodes.refresh(); }}>{t("common.retry")}</Button></Alert>}
    {nodes.error && !nodes.draft && !nodes.target && <Alert status="danger" role="alert"><Alert.Description>{nodes.error}</Alert.Description></Alert>}
    {nodes.notice && !nodes.draft && <pre className="node-output" role="status">{nodes.notice}</pre>}
    {nodes.loading && !nodes.nodes.length ? <Spinner aria-label={t("common.loading")} /> : nodes.nodes.length ? <NodeList nodes={nodes} /> : !nodes.listError && <p className="node-help">{t("features.noNodes")}</p>}
    {!nodes.loading && !nodes.listError && <NodeJobs nodes={nodes} />}
    <NodeEditor nodes={nodes} /><NodeCommand nodes={nodes} />
  </section>;
}
