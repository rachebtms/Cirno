import { Accordion, Button } from "@heroui/react";
import { memoryTitle } from "../model/presentation";
import { BookOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { InlineError } from "@/ui/feedback/InlineError";
import { SkeletonStatus } from "@/ui/feedback/SkeletonStatus";
import type { MemoryRecord } from "@/lib/contracts/memory";
import type { useMemorySearch } from "../model/useMemorySearch";

export function MemoryResults({
  search,
  onInspect,
}: {
  search: ReturnType<typeof useMemorySearch>;
  onInspect: (record: MemoryRecord) => void;
}) {
  const { t } = useTranslation();
  const snapshot = search.snapshot,
    result = snapshot?.result;
  const records = result?.memories ?? [];
  return (
    <section className="memory-results" aria-label={t("features.memorySources")}>
      <InlineError message={search.error} />
      {search.loading && !result && (
        <SkeletonStatus label={t("settings.loading")} className="memory-result-skeleton">
          {[0, 1, 2].map((index) => (
            <div key={index}>
              <span />
              <span />
            </div>
          ))}
        </SkeletonStatus>
      )}
      {snapshot &&
        (snapshot.query.query ||
          result?.warning_code ||
          result?.warning ||
          result?.embedding_index_pending) && (
          <div className="memory-retrieval" role="status">
            {snapshot.query.query && <p>{t("memoryLibrary.resultsFor", { query: snapshot.query.query })}</p>}
            {snapshot.query.query && result?.engine && (
              <p>{t("memoryLibrary.searchEngine", { mode: t(`memoryLibrary.${result.engine}Mode`) })}</p>
            )}
            {result?.warning_code && (
              <p>
                {t(`memoryLibrary.fallback_${result.warning_code}`, {
                  defaultValue: result.warning ?? result.warning_code,
                })}
              </p>
            )}
            {result?.warning && (
              <Accordion>
                <Accordion.Item id="reason">
                  <Accordion.Heading>
                    <Accordion.Trigger>
                      {t("memoryLibrary.searchDetails")}
                      <Accordion.Indicator />
                    </Accordion.Trigger>
                  </Accordion.Heading>
                  <Accordion.Panel>
                    <p>{result.warning}</p>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>
            )}
            {result?.embedding_index_pending && <p>{t("memoryLibrary.indexPending")}</p>}
          </div>
        )}
      {result && !records.length && (
        <p className="memory-empty">
          {t(snapshot!.query.query ? "memoryLibrary.noMatches" : "features.noMemorySources")}
        </p>
      )}
      <ul className="memory-record-list">
        {records.map((memory) => (
          <li key={memory.id}>
            <Button
              variant="ghost"
              aria-label={memoryTitle(memory, t)}
              className="memory-record"
              onPress={() => onInspect(memory)}
            >
              <BookOpen size={18} />
              <span className="memory-record-description">
                <span className="memory-record-title">{memoryTitle(memory, t)}</span>
                <span className="memory-hint">
                  {t(`memoryLibrary.${memory.layer}`)} · {t(`memoryLibrary.${memory.scope}`)} ·{" "}
                  {t(`memoryLibrary.${memory.status}`)} ·{" "}
                  {t("memoryLibrary.revision", { revision: memory.revision })}
                </span>
                {memory.snippet && <span className="memory-record-snippet">{memory.snippet}</span>}
              </span>
            </Button>
          </li>
        ))}
      </ul>
      {result?.has_more && (
        <Button
          variant="secondary"
          size="sm"
          isDisabled={search.loading}
          isPending={search.loading}
          onPress={() => {
            void search.more();
          }}
        >
          {t("memoryLibrary.more")}
        </Button>
      )}
    </section>
  );
}
