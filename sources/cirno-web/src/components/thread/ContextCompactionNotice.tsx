import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";
import type { UIContextCompaction } from "@/lib/types";

export function ContextCompactionNotice({ compaction }: { compaction: UIContextCompaction }) {
  const { t } = useTranslation();
  const titleFor = (attempt: UIContextCompaction) => t(attempt.reason
    ? `thread.compaction.reasons.${attempt.reason}.${attempt.phase}`
    : `thread.compaction.${attempt.phase}`);
  const attempts = compaction.attempts ?? [compaction];
  const title = titleFor(compaction);
  const expandable = attempts.length > 1 || compaction.phase === "failed";

  return <div role={compaction.announce ? "status" : undefined}
    aria-live={compaction.announce ? "polite" : undefined} aria-busy={compaction.phase === "started"}
    data-context-compaction={compaction.phase}
    className="mx-auto flex w-full max-w-[49.5rem] items-start justify-center gap-3 py-2 text-xs text-muted-foreground">
    <span aria-hidden className="mt-2.5 h-px min-w-4 max-w-16 flex-1 bg-border/60" />
    <div className={cn("min-w-0 text-center leading-5", compaction.phase === "failed" && "text-destructive/80")}>
      {expandable ? <details className="group">
        <summary className="cursor-pointer rounded-control px-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          {title}{attempts.length > 1 ? <span className="ml-2 whitespace-nowrap">{t("thread.compaction.attempts", { count: attempts.length })}</span> : null}
        </summary>
        <ol className="mt-2 space-y-2 rounded-control bg-muted/40 p-3 text-left text-muted-foreground">
          {attempts.map((attempt, index) => <li key={attempt.id} className="break-words">
            <p>{t("thread.compaction.attempt", { number: index + 1 })} · {titleFor(attempt)}</p>
            {attempt.phase === "failed" ? <p className="whitespace-pre-wrap text-destructive/80">{attempt.error || t("thread.compaction.errorUnavailable")}</p> : null}
          </li>)}
        </ol>
      </details> : <p>{title}</p>}
    </div>
    <span aria-hidden className="mt-2.5 h-px min-w-4 max-w-16 flex-1 bg-border/60" />
  </div>;
}
