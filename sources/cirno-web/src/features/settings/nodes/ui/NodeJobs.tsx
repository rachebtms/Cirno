import { Button, Card } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { NodesController } from "../model/useNodes";

export function NodeJobs({ nodes }: { nodes: NodesController }) {
  const { t, i18n } = useTranslation();
  const time = (value: string) => new Date(value).toLocaleString(i18n.language);
  return <section className="node-jobs"><header><h2>{t("features.jobs")}</h2><Button size="sm" variant="ghost" isDisabled={nodes.busy || nodes.loading} onPress={() => { void nodes.refresh(); }}>{t("features.refreshList")}</Button></header>
    {nodes.jobs.length ? nodes.jobs.map(job => <Card key={job.id}><Card.Content>
      <pre className="node-job-command">{job.command}</pre><p className="node-job-state">{t(`features.nodeJobStates.${job.state}`, { defaultValue: job.state })} · {job.id}</p>
      <p className="node-job-state">{job.checked_at ? t("features.nodeJobChecked", { time: time(job.checked_at) }) : t("features.nodeJobNotChecked")}</p>
      {job.finished_at && <p className="node-job-state">{t("features.nodeJobFinished", { time: time(job.finished_at) })}</p>}
      {job.check_error && <p className="node-job-check-error" role="status">{t("features.nodeJobCheckError", { error: job.check_error })}</p>}
      <div className="node-actions"><Button size="sm" variant="secondary" isDisabled={nodes.busy} onPress={() => { void nodes.readJob(job); }}>{t("features.readStatus")}</Button>
        {!(["completed", "failed", "stopped"].includes(job.state)) && <Button size="sm" variant="ghost" isDisabled={nodes.busy} onPress={() => { void nodes.stopJob(job); }}>{t("features.stop")}</Button>}</div>
      {(job.error || job.submission_error || job.verification_error) && <pre className="node-output">{[job.error, job.submission_error, job.verification_error].filter(Boolean).join("\n")}</pre>}
      {job.output && <pre className="node-output">{job.output}</pre>}
    </Card.Content></Card>) : <p>{t("features.noJobs")}</p>}
  </section>;
}
