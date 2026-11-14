import "./skill-detail.css";
import { Accordion, Button, Modal } from "@heroui/react";
import { RefreshCw, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SkillSummary } from "@/lib/contracts/skills";
import { InlineError } from "@/ui/feedback/InlineError";
import { SkeletonStatus } from "@/ui/feedback/SkeletonStatus";
import { ToggleField } from "@/ui/fields/ToggleField";
import { skillSourceLabel, skillStatus } from "../model/presentation";
import type { SkillInjectionSettings } from "../model/injection";
import { useSkillService } from "../model/service";
import { useSkillDetail } from "../model/useSkillDetail";
import { SkillActionDialog } from "./SkillActionDialog";
import { SkillDescription } from "./SkillDescription";
import { SkillRequirements } from "./SkillRequirements";

export function SkillDetailDialog({ skill, onClose, injection }: {
  skill: SkillSummary; onClose: () => void; injection?: SkillInjectionSettings;
}) {
  const { t } = useTranslation(),
    service = useSkillService();
  const state = useSkillDetail(service, skill, onClose),
    { read, mutation } = state;
  const detail = read.value,
    active = detail ?? skill,
    status = skillStatus(active, t),
    saving = mutation.busy || injection?.saving === true,
    busy = saving || read.loading,
    selected = injection?.names.includes(active.name) ?? false,
    declared = active.always && active.available && active.enabled !== false;
  return (
    <>
      <Modal.Backdrop
        isOpen
        isDismissable={!saving}
        isKeyboardDismissDisabled={saving}
        onOpenChange={(open) => {
          if (!open && !saving) onClose();
        }}
      >
        <Modal.Container size="lg">
          <Modal.Dialog className="skill-detail">
            <Modal.Header>
              <div className="skill-detail-title">
                <Modal.Heading>{active.name}</Modal.Heading>
                <Button
                  variant="ghost"
                  size="sm"
                  isIconOnly
                  isDisabled={busy}
                  aria-label={t("features.refresh")}
                  onPress={() => {
                    void state.refresh();
                  }}
                >
                  <RefreshCw size={16} />
                </Button>
              </div>
              <Modal.CloseTrigger isDisabled={saving} />
              <p className="skill-detail-meta">
                {skillSourceLabel(active.source, t)} · <status.Icon size={14} />
                {status.label}
              </p>
            </Modal.Header>
            <Modal.Body>
              <SkillDescription content={active.description} />
              <InlineError message={!active.available ? active.unavailable_reason : null} />
              {read.loading && !detail && (
                <SkeletonStatus label={t("settings.skills.loadingDetail")} className="skill-detail-skeleton">
                  <span />
                  <span />
                  <span />
                </SkeletonStatus>
              )}
              {detail && (
                <>
                  <ToggleField
                    label={t("settings.skills.enabledControl")}
                    description={t("settings.skills.enabledDescription")}
                    selected={detail.enabled !== false}
                    disabled={busy}
                    onChange={() => {
                      void state.toggle();
                    }}
                  />
                  {injection && <ToggleField
                    label={t("settings.skills.fixedControl")}
                    description={<span className="skill-injection-description">
                      <span>{t("settings.skills.fixedDescription")}</span>
                      {declared && <span>{t("settings.skills.fixedDeclared")}</span>}
                    </span>}
                    selected={selected || !!declared}
                    disabled={busy || !!declared || (!active.available || active.enabled === false) && !selected}
                    onChange={next => injection.setSelected(active.name, next)}
                  />}
                  {detail.enabled !== false && (
                    <SkillRequirements
                      detail={detail}
                      busy={busy}
                      onRefresh={() => {
                        void state.refresh();
                      }}
                    />
                  )}
                  <Accordion>
                    <Accordion.Item id="instructions">
                      <Accordion.Heading>
                        <Accordion.Trigger>
                          {t("settings.skills.instructionsTitle")}
                          <Accordion.Indicator />
                        </Accordion.Trigger>
                      </Accordion.Heading>
                      <Accordion.Panel>
                        <pre className="skill-instructions">
                          {detail.raw_markdown || t("settings.skills.rawInstructionsEmpty")}
                        </pre>
                      </Accordion.Panel>
                    </Accordion.Item>
                  </Accordion>
                  {(active.deletable ?? active.source === "home") && (
                    <section className="skill-delete">
                      <div>
                        <h3>{t("settings.skills.deleteTitle")}</h3>
                        <p>{t("settings.skills.deleteDescription")}</p>
                      </div>
                      <Button variant="danger-soft" size="sm" isDisabled={busy} onPress={state.requestDelete}>
                        <Trash2 size={15} />
                        {t("settings.skills.deleteAction")}
                      </Button>
                    </section>
                  )}
                </>
              )}
            </Modal.Body>
            {(read.error || injection?.error || (mutation.error && !state.deleting)) && (
              <Modal.Footer className="skill-action-footer">
                <InlineError message={read.error || injection?.error || mutation.error} />
                {(read.error || injection?.error) && (
                  <Button
                    variant="secondary"
                    size="sm"
                    isDisabled={busy}
                    onPress={() => {
                      if (read.error) void state.refresh();
                      else injection?.retry();
                    }}
                  >
                    <RefreshCw size={15} />
                    {t("settings.skills.retry")}
                  </Button>
                )}
              </Modal.Footer>
            )}
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
      {state.deleting && (
        <SkillActionDialog
          title={t("settings.skills.deleteConfirmTitle", { name: active.name })}
          description={<p>{t("settings.skills.deleteConfirmDescription")}</p>}
          action={t("settings.skills.deleteConfirmAction")}
          danger
          operation={mutation}
          onClose={state.cancelDelete}
          onConfirm={state.remove}
        />
      )}
    </>
  );
}
