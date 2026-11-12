import { useTranslation } from "react-i18next";
import type { LearningRetryReport } from "../../../packages/client-events/notifications";
import { LearningUpdateList } from "./LearningFailureNotice";

export function LearningRetryNotice({ report, active }: { report: LearningRetryReport; active: boolean }) {
  const { t } = useTranslation();
  const previous = new Set(report.previously_saved.map(item => item.id));
  const newlySaved = report.saved.filter(item => !previous.has(item.id));
  return <div className="mt-2 space-y-2 text-left text-muted-foreground">
    <p>{t("thread.compaction.retry.checkpointUnchanged")}</p>
    {!active && report.mode !== "pending" ? <>
      {report.outcome === "not_found" ? <p>{t("thread.compaction.retry.notFoundHelp")}</p> : <>
        <p>{t("thread.compaction.retry.savedCounts", { newCount: newlySaved.length, previousCount: report.previously_saved.length })}</p>
        <p>{(["memory", "document", "input"] as const).map(kind =>
          `${t(`thread.compaction.learningKinds.${kind}`)}: ${report.saved.filter(item => item.kind === kind).length}`,
        ).join(" · ")}</p>
        {report.outcome === "no_updates" ? <p>{t("thread.compaction.retry.noUpdatesHelp")}</p> : null}
        <LearningUpdateList title={t("thread.compaction.learningSaved")} items={report.saved} />
        <LearningUpdateList title={t("thread.compaction.learningPending")} items={report.pending} />
        {report.mode === "regenerate" ? <LearningUpdateList title={t("thread.compaction.retry.originalProposals")} items={report.requested} /> : null}
      </>}
      <p>{t(`thread.compaction.retry.${report.model_called ? "modelCalled" : "modelNotCalled"}`)}</p>
      {report.mode === "replay" || report.mode === "regenerate" ? <p>{t(`thread.compaction.retry.mode.${report.mode}`)}</p> : null}
    </> : null}
    {report.source ? <p className="break-all">{t("thread.compaction.learningSource")}: <code>{report.source}</code></p> : null}
  </div>;
}
