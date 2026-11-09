import { useState } from "react";
import { ModelCapabilityFields } from "./ModelCapabilityFields";
import { Accordion, Alert, Button, Description, Form, Modal } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { ModelsSettingsProps } from "../model/contracts";
import type { ModelSettings } from "../model/useModelSettings";
import { PresetConnectionFields } from "./PresetConnectionFields";
import { ModelAPIControl } from "../ModelAPIControl";
import { ModelAdvancedFields } from "../ModelAdvancedFields";
import { ProviderParameterFields } from "../../providers/ProviderParameterFields";
import { InlineError } from "@/ui/feedback/InlineError";
export function ModelPresetEditor({
  model,
  options,
}: {
  model: ModelSettings;
  options: ModelsSettingsProps;
}) {
  const { t } = useTranslation();
  const { form, setForm, creating, editCompletion: edits } = options;
  const [probing, setProbing] = useState(false);
  const busy = options.saving || options.creatingSaving || probing;
  async function close() {
    if (busy) return;
    if (!creating && edits.needsCompletion() && !(await edits.commit())) return;
    model.setEditorOpen(false);
    if (creating) options.onCancelCreate();
  }
  const apiProvider =
    model.selectedProvider ??
    options.settings.providers.find(
      (row) =>
        row.id ===
        (model.resolvedAutomaticAPI?.provider ?? model.selectedPreset?.resolved_provider),
    );
  return (
    <Modal.Backdrop
      isOpen={model.editorOpen && (creating || model.selectedPreset !== null)}
      onOpenChange={(open) => {
        if (!open) void close();
      }}
      isDismissable={!busy}
      isKeyboardDismissDisabled={busy}
    >
      <Modal.Container size="lg">
        <Modal.Dialog className="model-preset-dialog">
          <Modal.Header>
            <Modal.Heading>
              {creating ? t("settings.models.newPreset") : model.selectedPreset?.name}
            </Modal.Heading>
            <Modal.CloseTrigger data-edit-action isDisabled={busy} />
          </Modal.Header>
          <div
            className="model-preset-form"
            onChangeCapture={edits.onChangeCapture}
            onFocusCapture={edits.onFocusCapture}
            onBlurCapture={edits.onBlurCapture}
          >
            <Form
              onSubmit={(event) => {
                event.preventDefault();
                if (!busy) options.onSave();
              }}
              className="model-preset-form"
            >
              <Modal.Body>
                <fieldset disabled={probing} className="model-preset-fields min-w-0 border-0 p-0">
                  <PresetConnectionFields model={model} options={options} />
                  {options.settings.model_capability_testing_supported && <ModelCapabilityFields key={`${options.editingPresetId}:${form.provider}:${form.model}`} presetId={creating ? undefined : options.editingPresetId} form={form} setForm={setForm} disabled={busy} onBusyChange={setProbing} />}
                  <Accordion
                    expandedKeys={model.advancedOpen ? ["advanced"] : []}
                    onExpandedChange={(keys) => {
                      void model.changeAdvanced(keys.has("advanced"));
                    }}
                  >
                    <Accordion.Item id="advanced">
                      <Accordion.Heading>
                        <Accordion.Trigger data-edit-action>
                          {t("settings.models.advancedOptions")}
                          <Accordion.Indicator />
                        </Accordion.Trigger>
                      </Accordion.Heading>
                      <Accordion.Panel>
                        <Accordion.Body className="model-preset-fields">
                          <div aria-busy={model.automaticAPI.loading}>
                            <ModelAPIControl
                              provider={apiProvider}
                              automaticAPI={model.resolvedAutomaticAPI?.api}
                              value={form.api}
                              onChange={(api) => setForm((previous) => ({ ...previous, api }))}
                            />
                          </div>
                          {model.automaticAPI.error && (
                            <div>
                              <InlineError message={model.automaticAPI.error} />
                              <Button
                                type="button"
                                size="sm"
                                variant="secondary"
                                onPress={() => {
                                  void model.automaticAPI.retry();
                                }}
                              >
                                {t("common.retry")}
                              </Button>
                            </div>
                          )}
                          <ModelAdvancedFields
                            maxTokens={form.maxTokens}
                            contextWindowTokens={form.contextWindowTokens}
                            idleCompactPercent={form.idleCompactPercent}
                            idleCompactKeepPercent={form.idleCompactKeepPercent}
                            temperature={form.temperature}
                            onChange={(patch) => {
                              if (creating && patch.contextWindowTokens !== undefined)
                                model.presetContextInitializedRef.current = true;
                              setForm((previous) => ({ ...previous, ...patch }));
                            }}
                          />
                          {options.settings.model_request_overrides_supported && (
                            <>
                              <Description>{t("settings.models.requestOverridesHint")}</Description>
                              <ProviderParameterFields
                                inherit
                                draft={creating}
                                disabled={options.saving || (!creating && options.dirty)}
                                onSave={creating ? undefined : options.onSaveRequestSettings}
                                fields={apiProvider?.advanced_fields ?? []}
                                form={form}
                                onChange={(patch) =>
                                  setForm((previous) => ({
                                    ...previous,
                                    ...patch,
                                  }))
                                }
                              />
                            </>
                          )}
                        </Accordion.Body>
                      </Accordion.Panel>
                    </Accordion.Item>
                  </Accordion>
                  {options.error && (
                    <Alert status="danger" role="alert">
                      <Alert.Description>{options.error}</Alert.Description>
                    </Alert>
                  )}
                </fieldset>
              </Modal.Body>
              <Modal.Footer>
                {!creating && model.selectedPreset && (
                  <Button
                    variant="danger-soft"
                    isDisabled={model.selectedPresetReferenced || busy || options.orderSaving}
                    aria-describedby={
                      model.selectedPresetReferenced ? "preset-delete-help" : undefined
                    }
                    onPress={() =>
                      options.onDeleteConfiguration(model.selectedPreset!, () => {
                        model.setEditorOpen(false);
                        model.setEditorRowKey(null);
                      })
                    }
                  >
                    {t("settings.actions.delete")}
                  </Button>
                )}
                {model.selectedPresetReferenced && (
                  <span id="preset-delete-help" className="sr-only">
                    {t("settings.models.removeBeforeDelete")}
                  </span>
                )}
                <Button data-edit-action variant="secondary" isDisabled={busy} onPress={() => void close()}>
                  {t("settings.actions.cancel")}
                </Button>
                <Button
                  type="submit"
                  data-edit-action
                  isPending={busy}
                  isDisabled={
                    (!creating && !options.dirty) ||
                    !model.selectedProviderConfigured ||
                    model.modelFieldsMissing ||
                    options.orderSaving
                  }
                >
                  {t("settings.actions.savePreset")}
                </Button>
              </Modal.Footer>
            </Form>
          </div>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
