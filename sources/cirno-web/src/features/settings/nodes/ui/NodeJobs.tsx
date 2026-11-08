import { Button, Card } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { NodesController } from "../model/useNodes";

export function NodeJobs({ nodes }: { nodes: NodesController }) {
  const { t } = useTranslation();
  return <section className="node-jobs"><header><h2>{t("features.jobs")}</h2><Button size="sm" variant="ghost" isDisabled={nodes.busy || nodes.loading} onPress={() => { void nodes.refresh(); }}>{t("features.refreshList")}</Button></header>
    {nodes.jobs.length ? nodes.jobs.map(job => <Card key={job.id}><Card.Content>
      <pre className="node-job-command">{job.command}</pre><p className="node-job-state">{job.state} · {job.id}</p>
      <div className="node-actions"><Button size="sm" variant="secondary" isDisabled={nodes.busy} onPress={() => { void nodes.readJob(job); }}>{t("features.readStatus")}</Button>
        <Button size="sm" variant="ghost" isDisabled={nodes.busy} onPress={() => { void nodes.stopJob(job); }}>{t("features.stop")}</Button></div>
      {(job.error || job.output) && <pre className="node-output">{job.error || job.output}</pre>}
    </Card.Content></Card>) : <p>{t("features.noJobs")}</p>}
  </section>;
}
