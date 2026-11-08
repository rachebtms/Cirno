import { Button, Modal, Tabs } from "@heroui/react";
import { useTranslation } from "react-i18next";
import { InlineError } from "@/ui/feedback/InlineError";
import { nextEvidenceCursor } from "../model/evidence-cursor";
import { useMemoryInspector } from "../model/useMemoryInspector";
import type { MemoryService } from "../model/service";
import type { MemoryRecord } from "@/lib/contracts/memory";
import { EvidenceView } from "./EvidenceView";
import { memoryTitle } from "../model/presentation";

export function MemoryInspector({
  service,
  memory,
  onClose,
}: {
  service: MemoryService;
  memory: MemoryRecord;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const inspector = useMemoryInspector(service, memory);
  const { record, versions, source } = inspector;
  const data = record.value;
  return (
    <Modal.Backdrop
      isOpen
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Modal.Container size="lg">
        <Modal.Dialog className="memory-inspector">
          <Modal.Header>
            <Modal.Heading>{memoryTitle(data ?? memory, t)}</Modal.Heading>
            <Modal.CloseTrigger />
            <p className="memory-hint">
              <code>{memory.id}</code> · {t("memoryLibrary.revision", { revision: inspector.revision })}
            </p>
          </Modal.Header>
          <Modal.Body>
            <Tabs selectedKey={inspector.view} onSelectionChange={(key) => inspector.selectView(String(key))}>
              <Tabs.List aria-label={t("features.memorySources")}>
                {(["record", "versions", "source"] as const).map((id, index) => (
                  <Tabs.Tab key={id} id={id}>
                    {t(`memoryLibrary.${["read", "history", "evidence"][index]}`)}
                    <Tabs.Indicator />
                  </Tabs.Tab>
                ))}
              </Tabs.List>
              <Tabs.Panel id="record">
                <InlineError message={record.error} />
                {record.error && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onPress={() => {
                      void inspector.reload();
                    }}
                  >
                    {t("common.retry")}
                  </Button>
                )}
                {record.loading && (
                  <p role="status" className="memory-hint">
                    {t("settings.loading")}
                  </p>
                )}
                {data && (
                  <div className="memory-read">
                    <dl className="memory-record-metadata">
                      <div>
                        <dt>{t("memoryLibrary.evidence")}</dt>
                        <dd>
                          <code>{data.source}</code>
                        </dd>
                      </div>
                      {memory.scope !== "user" && (
                        <div>
                          <dt>{t("memoryLibrary.scope")}</dt>
                          <dd>{memory.owner_title ?? memory.project_id ?? memory.session_key}</dd>
                        </div>
                      )}
                      {data.observed_at && (
                        <div>
                          <dt>{t("memoryLibrary.observedAt")}</dt>
                          <dd>
                            <code>{data.observed_at}</code>
                          </dd>
                        </div>
                      )}
                      {!!data.tags.length && (
                        <div>
                          <dt>{t("memoryLibrary.tags")}</dt>
                          <dd>{data.tags.join(" · ")}</dd>
                        </div>
                      )}
                    </dl>
                    <pre className="memory-document">{data.content}</pre>
                    {!!data.links.length && (
                      <section>
                        <h3>{t("memoryLibrary.links")}</h3>
                        <ul className="memory-detail-list">
                          {data.links.map((link) => (
                            <li key={`${link.source}:${link.target}:${link.relation}`}>
                              <span>{link.relation}: </span>
                              <code>
                                {link.source} → {link.target}
                              </code>
                              <p>{link.evidence}</p>
                            </li>
                          ))}
                        </ul>
                      </section>
                    )}
                  </div>
                )}
              </Tabs.Panel>
              <Tabs.Panel id="versions">
                <InlineError message={versions.error} />
                {versions.loading && (
                  <p role="status" className="memory-hint">
                    {t("settings.loading")}
                  </p>
                )}
                {versions.error && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onPress={() => {
                      void inspector.loadVersions();
                    }}
                  >
                    {t("common.retry")}
                  </Button>
                )}
                <ul className="memory-version-list">
                  {versions.value?.revisions.map((version) => (
                    <li key={version.revision}>
                      <Button
                        variant={version.revision === inspector.revision ? "secondary" : "ghost"}
                        onPress={() => {
                          void inspector.openRevision(version.revision);
                        }}
                      >
                        {t("memoryLibrary.revision", { revision: version.revision })}
                      </Button>
                      <time>{version.updated_at}</time>
                    </li>
                  ))}
                </ul>
              </Tabs.Panel>
              <Tabs.Panel id="source">
                <EvidenceView inspector={inspector} memoryId={memory.id} />
              </Tabs.Panel>
            </Tabs>
          </Modal.Body>
          {inspector.view === "source" &&
            (source.error || (source.value && nextEvidenceCursor(source.value))) && (
              <Modal.Footer className="memory-source-footer">
                <InlineError message={source.error} />
                {source.error ? (
                  <Button
                    variant="secondary"
                    isDisabled={source.loading}
                    isPending={source.loading}
                    onPress={() => {
                      void inspector.readSource();
                    }}
                  >
                    {t("common.retry")}
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    isDisabled={source.loading}
                    isPending={source.loading}
                    onPress={inspector.more}
                  >
                    {t("memoryLibrary.sourceMore")}
                  </Button>
                )}
              </Modal.Footer>
            )}
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
