import { Button } from "@heroui/react";
import { BookOpen, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { useMemoryInspector } from "../model/useMemoryInspector";

export function EvidenceView({
  inspector,
  memoryId,
}: {
  inspector: ReturnType<typeof useMemoryInspector>;
  memoryId: string;
}) {
  const { t } = useTranslation();
  const { source } = inspector;
  const page = source.value;
  return (
    <section className="memory-evidence">
      <div className="memory-evidence-actions">
        <Button
          variant="ghost"
          size="sm"
          isDisabled={source.loading}
          onPress={() => {
            void inspector.readSource({ id: memoryId, revision: inspector.revision });
          }}
        >
          <RefreshCw size={14} />
          {t("features.refresh")}
        </Button>
      </div>
      {source.loading && (
        <p role="status" className="memory-hint">
          {t("settings.loading")}
        </p>
      )}
      {page && (
        <>
          <div className="memory-evidence-heading">
            <code>{page.source}</code>
            <span>{t("memoryLibrary.revision", { revision: page.revision })}</span>
          </div>
          {page.note && <p className="memory-hint">{page.note}</p>}
          <pre className="memory-document">
            {page.content ?? page.lines?.map((line) => `${line.line}: ${line.text}`).join("\n")}
          </pre>
          <div className="memory-evidence-references">
            {page.source_refs
              ?.filter((ref) => ref.memory_id)
              .map((ref, index) => (
                <Button
                  key={`${ref.memory_id}:${ref.revision}:${index}`}
                  variant="ghost"
                  size="sm"
                  isDisabled={source.loading}
                  onPress={() => {
                    void inspector.readSource({
                      id: ref.memory_id!,
                      revision: ref.revision,
                      start_line: ref.start_line ?? 1,
                    });
                  }}
                >
                  <BookOpen size={15} />
                  {t("memoryLibrary.archivedEvidenceTitle")} · {ref.memory_id!.slice(-6)}
                  {ref.revision != null && ` · ${t("memoryLibrary.revision", { revision: ref.revision })}`}
                </Button>
              ))}
          </div>
        </>
      )}
    </section>
  );
}
