import { Alert, Button, Card, Spinner } from "@heroui/react";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useModelSettings } from "./model/useModelSettings";
import type { ModelsSettingsProps } from "./model/contracts";
import { ModelPresetList } from "./ui/ModelPresetList";
import { ModelPresetEditor } from "./ui/ModelPresetEditor";
import "./models.css";
export function ModelsSettings(props: ModelsSettingsProps) {
  const { t } = useTranslation();
  const model = useModelSettings(props);
  const editorVisible = model.editorOpen && (props.creating || model.selectedPreset !== null);
  return <section className="models-settings" aria-label={t("settings.models.presets")}>
    <header className="models-actions"><Button variant="secondary" onClick={event => props.onManageProviders(event.currentTarget as HTMLButtonElement)}>{t("settings.providers.manageProviders")}</Button>
      <Button isDisabled={model.callOrderBusy} onClick={event => { model.editorTriggerRef.current = event.currentTarget as HTMLButtonElement; model.setEditorRowKey(null); model.setEditorOpen(true); props.onBeginCreate(); }}><Plus size={17} />{t("settings.models.newPreset")}</Button>
    </header>
    {props.error && !editorVisible && <Alert status="danger" role="alert"><Alert.Content>{props.error}</Alert.Content></Alert>}
    {model.presetRows.length ? <ModelPresetList model={model} options={props} /> : <Card><Card.Content><p>{t("settings.models.noPresets")}</p><p className="provider-secondary">{t("settings.models.newPresetHelp")}</p></Card.Content></Card>}
    {props.orderSaving && <p role="status" className="model-order-saving"><Spinner size="sm" />{t("settings.actions.saving")}</p>}
    <ModelPresetEditor model={model} options={props} />
  </section>;
}
