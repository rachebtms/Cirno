import { Accordion, Button, Card } from "@heroui/react";
import { Database, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { InlineError } from "@/ui/feedback/InlineError";
import { fmtDateTime } from "@/lib/format-time";
import type { MemoryStatus } from "@/lib/contracts/memory";
import type { useMemoryMaintenance } from "../model/useMemoryMaintenance";
import { LearningFailureNotice } from "@/components/thread/LearningFailureNotice";

export function MemoryStats({
  data,
  error,
  maintenance,
  onRefresh,
  refreshing,
}: {
  data: MemoryStatus | null;
  error: string | null;
  maintenance: ReturnType<typeof useMemoryMaintenance>;
  onRefresh?: () => void;
  refreshing?: boolean;
}) {
  const { t } = useTranslation();
  const tr = (key: string) => t(`memoryLibrary.${key}`);
  return (
    <section className="memory-index-status">
      <InlineError message={error} />
      {!data && onRefresh && <Button variant="secondary" size="sm" isPending={refreshing} onPress={onRefresh}>{t("features.refresh")}</Button>}
      {data && (
        <Card>
          <Card.Header>
            <Database size={18} />
            <h3>{tr("statusTitle")}</h3>
            {onRefresh && <Button variant="ghost" size="sm" isIconOnly className="memory-status-refresh"
              aria-label={t("memoryGraph.refreshIndex")} isPending={refreshing} onPress={onRefresh}><RefreshCw size={16} /></Button>}
          </Card.Header>
          <Card.Content>
            <div className="memory-index-counts">
              <span>
                {t("memoryLibrary.indexed", { count: Object.values(data.counts).reduce((a, b) => a + b, 0) })}
              </span>
              <span>{t("memoryLibrary.pending", { count: data.pending })}</span>
              <span>{t("memoryLibrary.failed", { count: data.failed + (data.consolidation_failed ?? 0) })}</span>
              <span>{t("memoryLibrary.indexSize", { size: (data.index_bytes / 1048576).toFixed(1) })}</span>
            </div>
            <p className="memory-hint">
              {tr("lastConsolidation")}: {data.last_consolidation ? fmtDateTime(data.last_consolidation.at) : tr("noConsolidation")}
            </p>
            <InlineError message={data.last_consolidation?.error ?? undefined} />
            {(data.consolidation_failures ?? []).map(failure => <LearningFailureNotice key={failure.source}
              failure={{ source: failure.source, error: failure.error ?? "", saved: failure.saved ?? [], pending: failure.pending ?? [] }} />)}
            <Accordion variant="surface">
              {!!data.receipts?.length && (
                <Accordion.Item id="receipts">
                  <Accordion.Heading>
                    <Accordion.Trigger>
                      {tr("dreamOutcomes")}
                      <Accordion.Indicator />
                    </Accordion.Trigger>
                  </Accordion.Heading>
                  <Accordion.Panel>
                    <ul className="memory-detail-list">
                      {data.receipts.map((receipt, index) => (
                        <li key={`${receipt.memory_id}:${index}`}>
                          <strong>{tr(`${receipt.outcome}Outcome`)}</strong> · {receipt.memory_id.slice(-6)} ·{" "}
                          {t("memoryLibrary.revision", { revision: receipt.input_revision })}
                          <p>{receipt.reason}</p>
                        </li>
                      ))}
                    </ul>
                  </Accordion.Panel>
                </Accordion.Item>
              )}
              {data.databases && (
                <Accordion.Item id="databases">
                  <Accordion.Heading>
                    <Accordion.Trigger>
                      {tr("databases")}
                      <Accordion.Indicator />
                    </Accordion.Trigger>
                  </Accordion.Heading>
                  <Accordion.Panel>
                    <dl className="memory-database-list">
                      {Object.entries(data.databases).map(([name, bytes]) => (
                        <div key={name}>
                          <dt>{name}</dt>
                          <dd>{(bytes / 1048576).toFixed(2)} MB</dd>
                        </div>
                      ))}
                    </dl>
                  </Accordion.Panel>
                </Accordion.Item>
              )}
              {!!data.failures?.length && (
                <Accordion.Item id="failures">
                  <Accordion.Heading>
                    <Accordion.Trigger>
                      {t("memoryLibrary.failed", { count: data.failed + (data.consolidation_failed ?? 0) })}
                      <Accordion.Indicator />
                    </Accordion.Trigger>
                  </Accordion.Heading>
                  <Accordion.Panel>
                    <ul className="memory-detail-list">
                      {data.failures.map((failure) => (
                        <li key={failure.memory_id}>
                          <code>{failure.memory_id}</code> ·{" "}
                          {t("memoryLibrary.revision", { revision: failure.revision })}
                          <p>{failure.error ?? tr("interrupted")}</p>
                        </li>
                      ))}
                    </ul>
                  </Accordion.Panel>
                </Accordion.Item>
              )}
            </Accordion>
          </Card.Content>
          <Card.Footer>
            <Button
              variant="secondary"
              size="sm"
              isDisabled={maintenance.busy}
              isPending={maintenance.busy && maintenance.action === "reindex"}
              onPress={() => {
                void maintenance.run("reindex");
              }}
            >
              <RefreshCw size={15} />
              {tr(maintenance.phase === "stopped" ? "rebuildMore" : "reindex")}
            </Button>
            {(data.consolidation_failed ?? 0) > 0 && (
              <Button
                variant="ghost"
                size="sm"
                isDisabled={maintenance.busy}
                isPending={maintenance.busy && maintenance.action === "retry"}
                onPress={() => {
                  void maintenance.run("retry");
                }}
              >
                {tr("retry")}
              </Button>
            )}
            {maintenance.busy && maintenance.action === "reindex" && (
              <Button variant="ghost" size="sm" onPress={maintenance.stop}>
                {t("features.stop")}
              </Button>
            )}
          </Card.Footer>
        </Card>
      )}
      <InlineError message={maintenance.error} />
      {maintenance.action === "reindex" && ["running", "complete", "stopped"].includes(maintenance.phase) && (
        <p role="status" className="memory-hint">
          {maintenance.phase === "running"
            ? t("memoryLibrary.rebuildProgress", { count: maintenance.scanned })
            : tr(maintenance.phase === "complete" ? "rebuildDone" : "rebuildMore")}
        </p>
      )}
    </section>
  );
}
