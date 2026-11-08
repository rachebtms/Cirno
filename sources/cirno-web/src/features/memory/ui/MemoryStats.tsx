import { Accordion, Button, Card } from "@heroui/react";
import { Database, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { InlineError } from "@/ui/feedback/InlineError";
import { fmtDateTime } from "@/lib/format-time";
import type { MemoryStatus } from "@/lib/contracts/memory";
import type { useMemoryMaintenance } from "../model/useMemoryMaintenance";

export function MemoryStats({
  data,
  error,
  maintenance,
}: {
  data: MemoryStatus | null;
  error: string | null;
  maintenance: ReturnType<typeof useMemoryMaintenance>;
}) {
  const { t } = useTranslation();
  const tr = (key: string) => t(`memoryLibrary.${key}`);
  return (
    <section className="memory-index-status">
      <InlineError message={error} />
      {data && (
        <Card>
          <Card.Header>
            <Database size={18} />
            <h3>{tr("statusTitle")}</h3>
          </Card.Header>
          <Card.Content>
            <div className="memory-index-counts">
              <span>
                {t("memoryLibrary.indexed", { count: Object.values(data.counts).reduce((a, b) => a + b, 0) })}
              </span>
              <span>{t("memoryLibrary.pending", { count: data.pending })}</span>
              <span>{t("memoryLibrary.failed", { count: data.failed })}</span>
              <span>{t("memoryLibrary.indexSize", { size: (data.index_bytes / 1048576).toFixed(1) })}</span>
            </div>
            <p className="memory-hint">
              {tr("lastDream")}: {data.last_dream ? fmtDateTime(data.last_dream.at) : tr("noDream")}
            </p>
            <InlineError message={data.last_dream?.error} />
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
                      {t("memoryLibrary.failed", { count: data.failed })}
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
            {data.failed > 0 && (
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
