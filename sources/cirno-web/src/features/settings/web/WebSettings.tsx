import { Accordion, Alert, Button, Card, Chip, Description, FieldError, Input, Label, ListBox, NumberField, Select, Spinner, TextField } from "@heroui/react";
import { useTranslation } from "react-i18next";
import { ToggleField } from "@/ui/fields/ToggleField";
import { ProviderIcon } from "../shared/ProviderIcon";
import { ProviderSecretField } from "../providers/ui/ProviderSecretField";
import type { WebSettingsProps } from "./model/contracts";
import { useWebSettings } from "./model/useWebSettings";
import "./web.css";

export function WebSettings(options: WebSettingsProps) {
  const { t } = useTranslation();
  const state = useWebSettings(options);
  const { settings, form, embedded, enabled = true, saving } = options;
  const validateNumber = (value: number) => Number.isFinite(value) ? null : t("settings.runtimeConfig.numberError");
  const error = state.missingCredential ? t("settings.byok.webSearch.missingCredential") : options.error || options.capabilityError;
  return <div className="web-settings" onChangeCapture={state.edits.onChangeCapture} onFocusCapture={state.edits.onFocusCapture} onBlurCapture={state.edits.onBlurCapture}>
    {embedded && <h2>{t("settings.sections.webSearch")}</h2>}
    {(embedded || enabled) && <Card><Card.Content className="web-fields">
      <Select value={form.provider} onChange={key => { if (key !== null) state.selectProvider(String(key)); }}>
        <Label>{t("settings.byok.webSearch.provider")}</Label><Select.Trigger><ProviderIcon provider={form.provider} showBrandLogos={options.showBrandLogos} compact /><Select.Value>{state.provider?.label}</Select.Value><Select.Indicator /></Select.Trigger>
        <Select.Popover><ListBox items={settings.web_search.providers}>{provider => <ListBox.Item id={provider.name} textValue={provider.label}>
          <ProviderIcon provider={provider.name} showBrandLogos={options.showBrandLogos} compact /><Label>{provider.label}</Label><ListBox.ItemIndicator />
        </ListBox.Item>}</ListBox></Select.Popover>
      </Select>
      {state.provider?.credential === "none" && <Chip variant="soft" color="success">{t("settings.byok.webSearch.noCredentialRequired")}</Chip>}
      {state.showKey && <div className="web-fields"><ProviderSecretField value={form.apiKey ?? ""} onChange={value => state.change("apiKey", value)}
        hint={state.hint} onEdit={options.onToggleKeyEditing} visible={options.keyVisible} onToggle={options.onToggleKey} />
        <p className="web-help">{t("settings.byok.webSearch.apiKeyHelp")}</p>
      </div>}
      {state.provider?.credential === "base_url" && <TextField value={form.baseUrl ?? ""} onChange={value => state.change("baseUrl", value)}>
        <Label>{t("settings.byok.webSearch.baseUrl")}</Label><Description>{t("settings.byok.webSearch.baseUrlHelp")}</Description><Input placeholder={t("settings.byok.webSearch.baseUrlPlaceholder")} autoComplete="off" spellCheck={false} />
      </TextField>}
      {state.installRequired && <Alert status="warning"><Alert.Description>{t("settings.capabilities.searchInstallOnSave")}</Alert.Description></Alert>}
      <Accordion><Accordion.Item id="advanced"><Accordion.Heading><Accordion.Trigger>{t("settings.providers.advancedOptions")}<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading><Accordion.Panel><Accordion.Body className="web-fields">
        <div className="web-numbers">
          <NumberField isRequired validationBehavior="aria" validate={validateNumber} value={form.maxResults ?? settings.web_search.max_results} onChange={value => state.change("maxResults", value)} minValue={1} maxValue={10}>
            <Label>{t("settings.rows.maxResults")}</Label><NumberField.Group><NumberField.DecrementButton /><NumberField.Input /><NumberField.IncrementButton /></NumberField.Group><FieldError />
          </NumberField>
          <NumberField isRequired validationBehavior="aria" validate={validateNumber} value={form.timeout ?? settings.web_search.timeout} onChange={value => state.change("timeout", value)} minValue={1} maxValue={120}>
            <Label>{t("settings.rows.timeout")} (s)</Label><NumberField.Group><NumberField.DecrementButton /><NumberField.Input /><NumberField.IncrementButton /></NumberField.Group><FieldError />
          </NumberField>
        </div>
        <ToggleField label={t("settings.rows.jinaReader")} description={t("settings.help.jinaReader")} selected={form.useJinaReader ?? settings.web.fetch.use_jina_reader} onChange={value => state.change("useJinaReader", value)} />
        {options.children}
      </Accordion.Body></Accordion.Panel></Accordion.Item></Accordion>
    </Card.Content></Card>}
    {error && <Alert status="danger" role="alert"><Alert.Description>{error}</Alert.Description></Alert>}
    {saving && <p role="status" className="web-save-status"><Spinner size="sm" />{t("settings.actions.saving")}</p>}
    {state.dirty && !saving && !error && !state.invalidNumbers && <p className="web-help">{t("settings.byok.webSearch.saveHint")}</p>}
    {((state.installRequired || state.invalidNumbers || options.error) && state.dirty) && <div className="web-actions">
      {(state.installRequired || state.invalidNumbers) && <Button variant="secondary" isDisabled={saving} onPress={options.onReset}>{t("settings.actions.cancel")}</Button>}
      {(state.installRequired || options.error) && <Button isPending={saving || options.olostepInstalling} isDisabled={state.missingCredential || state.invalidNumbers} onPress={options.onSave}>{t(state.installRequired ? "settings.cirnoFeatures.installConfirmAction" : "settings.actions.save")}</Button>}
    </div>}
    {!embedded && options.requiresRestartPending && !state.dirty && <div className="web-actions"><p className="web-help">{t("settings.status.savedRestartApply")}</p>
      {options.onRestart && <Button variant="secondary" isPending={options.isRestarting} onPress={options.onRestart}>{t("app.system.restart")}</Button>}
    </div>}
  </div>;
}
