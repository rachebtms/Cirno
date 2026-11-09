import {
  Button,
  Description,
  FieldError,
  Input,
  Label,
  ListBox,
  Select,
  TextField,
} from "@heroui/react";
import { Plus, Settings2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { suggestedPresetName } from "../modelDraft";
import { ModelCatalogField } from "./ModelCatalogField";
import type { ModelSettings } from "../model/useModelSettings";
import type { ModelsSettingsProps } from "../model/contracts";
import { PresetReasoningFields } from "./PresetReasoningFields";
export function PresetConnectionFields({
  model,
  options,
}: {
  model: ModelSettings;
  options: ModelsSettingsProps;
}) {
  const { t } = useTranslation();
  const { form, setForm, creating, settings } = options;
  const catalogProvider =
    model.selectedProvider ??
    settings.providers.find((row) => row.id === model.selectedPreset?.resolved_provider);
  return (
    <div className="model-preset-fields">
      <TextField
        isRequired
        validationBehavior="aria"
        value={form.presetName}
        isInvalid={Boolean(options.presetNameError)}
        onChange={(presetName) => {
          model.suggestedPresetNameRef.current = null;
          options.onClearPresetNameError();
          setForm((previous) => ({ ...previous, presetName }));
        }}
      >
        <Label>{t("settings.models.presetName")}</Label>
        <Description>{t("settings.models.presetNameHelp")}</Description>
        <Input
          autoFocus={creating}
          ref={model.presetNameInputRef}
          placeholder={t("settings.models.presetNamePlaceholder")}
        />
        <FieldError>
          {options.presetNameError && <span role="alert">{options.presetNameError}</span>}
        </FieldError>
      </TextField>
      {!creating && model.selectedPreset && (
        <TextField isReadOnly value={model.selectedPreset.id}>
          <Label>Model ID</Label>
          <Input />
        </TextField>
      )}
      <Select
        value={model.providerValue || null}
        onChange={(key) => {
          if (key !== null) model.selectProvider(String(key));
        }}
      >
        <Label>{t("settings.rows.provider")}</Label>
        <Select.Trigger>
          <Select.Value />
          <Select.Indicator />
        </Select.Trigger>
        <Select.Popover>
          <ListBox items={model.providerOptions}>
            {(provider) => (
              <ListBox.Item id={provider.id} textValue={provider.name}>
                {provider.name}
                <ListBox.ItemIndicator />
              </ListBox.Item>
            )}
          </ListBox>
        </Select.Popover>
      </Select>
      <div className="provider-actions">
        <Button
          variant="secondary"
          onClick={(event) =>
            options.onAddProvider(event.currentTarget as HTMLButtonElement, model.selectProvider)
          }
        >
          <Plus size={16} />
          {t("settings.providers.addProvider")}
        </Button>
        {model.selectedProvider && (
          <Button
            variant="ghost"
            onClick={(event) =>
              options.onConfigureProvider(
                model.selectedProvider!.id,
                event.currentTarget as HTMLButtonElement,
              )
            }
          >
            <Settings2 size={16} />
            {t("settings.configure")}
          </Button>
        )}
      </div>
      {model.selectedProviderNeedsSignIn && (
        <div>
          <Description>{t("settings.oauth.signInBeforeSaving")}</Description>
          <Button
            isPending={model.selectedProviderSigningIn}
            isDisabled={!model.selectedProvider?.oauth_login_supported}
            onPress={() => options.onProviderOAuthLogin(model.selectedProvider!.id)}
          >
            {t("settings.oauth.signIn")}
          </Button>
        </div>
      )}
      <ModelCatalogField
        key={form.provider}
        token={options.token}
        onSignIn={options.onProviderOAuthLogin}
        signingIn={model.selectedProviderSigningIn}
        provider={catalogProvider}
        value={form.model}
        onSelect={options.editCompletion.complete}
        onChange={(id, info) => {
          const context = info?.context_window;
          const initialize =
            creating &&
            !model.presetContextInitializedRef.current &&
            typeof context === "number" &&
            Number.isSafeInteger(context) &&
            context > 0;
          if (initialize) model.presetContextInitializedRef.current = true;
          const suggest =
            creating &&
            (!form.presetName.trim() || form.presetName === model.suggestedPresetNameRef.current);
          const name = suggest ? suggestedPresetName(id, settings.model_presets) : form.presetName;
          if (suggest) model.suggestedPresetNameRef.current = name;
          setForm((previous) => ({
            ...previous,
            model: id,
            contextWindowTokens: initialize ? context : previous.contextWindowTokens,
            api: id === previous.model ? previous.api : null,
            imageInput: id === previous.model ? previous.imageInput : null,
            videoInput: id === previous.model ? previous.videoInput : null,
            presetName: name,
          }));
        }}
      />
      <PresetReasoningFields model={model} options={options} provider={catalogProvider} />
    </div>
  );
}
