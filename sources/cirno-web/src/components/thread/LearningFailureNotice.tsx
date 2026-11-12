import { useTranslation } from "react-i18next";
import type { LearningFailure } from "../../../packages/client-events/notifications";

export function LearningFailureNotice({ failure }: { failure: LearningFailure }) {
  const { t } = useTranslation();
  return <div className="mt-2 space-y-2 text-left text-muted-foreground">
    <p>{t("thread.compaction.learningFailedHelp")}</p>
    {(["saved", "pending"] as const).map(state => failure[state].length ? <div key={state}>
      <p>{t(`thread.compaction.learning${state === "saved" ? "Saved" : "Pending"}`)}</p>
      <ul className="list-disc pl-4">{failure[state].map(item => <li key={item.id} className="break-words">
        {t(`thread.compaction.learningKinds.${item.kind}`, { defaultValue: item.kind })}{item.label ? `: ${item.label}` : ""}
      </li>)}</ul>
    </div> : null)}
    <p className="whitespace-pre-wrap text-destructive/80">{failure.error}</p>
    <p className="break-all">{t("thread.compaction.learningSource")}: <code>{failure.source}</code></p>
    <p>{t("thread.compaction.learningRetryHelp")}</p>
    <code className="block break-all select-all">/consolidate retry {failure.source}</code>
  </div>;
}
