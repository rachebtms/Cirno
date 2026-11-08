import { Accordion, Alert, Button, Form, Spinner } from "@heroui/react";
import { Clipboard } from "lucide-react";
import { useTranslation } from "react-i18next";
import { InlineError } from "@/ui/feedback/InlineError";
import { ChannelRuntimeError } from "../ChannelRuntimeError";
import { ToggleField } from "@/ui/fields/ToggleField";
import { ChannelFieldGroups } from "../fields/ChannelFieldGroups";
import { ChannelAdvanced } from "./ChannelAdvanced";
import { ChannelSetupActions } from "./ChannelSetupHelpers";
import { ChannelValidationResult } from "../ChannelValidationResult";
import type { ChannelSetupViewProps } from "./contracts";
export function ChannelSetupView(props: ChannelSetupViewProps) {
  const { t } = useTranslation(),
    mode = props.setup.mode ?? "credentials";
  const hasAdvanced = Boolean(
    props.advancedFields.length ||
      props.savedSecretFields.length ||
      props.availablePresets.length,
  );
  const form = {
    values: props.fieldValues,
    configuredFields: props.configuredFields,
    visibleSecrets: props.visibleSecrets,
    clearedSecrets: props.clearedSecrets,
    errors: props.fieldErrors,
    onChange: props.onChangeField,
    onToggleSecret: props.onToggleSecret,
    onClearSecret: props.onClearSecret,
    disabled: props.actionPending,
    secretActionsDisabled: props.autoSaving || props.actionPending,
  };
  return (
    <Form
      className="channel-setup-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (mode === "credentials") props.onSubmit();
      }}
    >
      <div className="channel-setup-heading">
        {props.header}
        <span role="status" aria-live="polite" className="channel-save-state">
          {props.autoSaving ? (
            <>
              <Spinner size="sm" />
              {t("settings.actions.saving")}
            </>
          ) : props.autoSaveState === "saved" ? (
            t("settings.channels.savedSettings")
          ) : null}
        </span>
      </div>
      {props.noticeTone === "danger" ? (
        <InlineError message={props.notice} />
      ) : (
        props.notice && (
          <Alert
            status={props.noticeTone === "success" ? "success" : "default"}
            role="status"
          >
            <Alert.Description>{props.notice}</Alert.Description>
          </Alert>
        )
      )}
      <ChannelRuntimeError message={props.feature.runtime_error} />
      {props.setup.privacyNotice && (
        <p className="channel-setup-hint">{props.setup.privacyNotice}</p>
      )}
      <ChannelSetupActions setup={props.setup} onNotice={props.onNotice} />
      {mode === "webui" && (
        <p className="channel-setup-hint">
          {t("settings.channels.managedByWebui")}
        </p>
      )}
      {mode === "connect" &&
        (props.connectFlow ?? (
          <div className="channel-manual-connect">
            <p>{t("settings.channels.connectPreview")}</p>
            {props.setup.command && (
              <>
                <code>{props.setup.command}</code>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onPress={props.onCopyCommand}
                >
                  <Clipboard size={16} />
                  {t("settings.channels.copyCommand")}
                </Button>
              </>
            )}
          </div>
        ))}
      {mode === "credentials" && (
        <ChannelFieldGroups
          fields={props.primaryFields}
          requirements={props.setup.requirements ?? []}
          sectionLabels={props.setup.sectionLabels}
          {...form}
        />
      )}
      {hasAdvanced && (
        <Accordion
          expandedKeys={props.advancedOpen ? new Set(["advanced"]) : new Set()}
          onExpandedChange={(keys) =>
            props.onAdvancedOpenChange(keys.has("advanced"))
          }
        >
          <Accordion.Item id="advanced">
            <Accordion.Heading>
              <Accordion.Trigger>
                {t("settings.channels.advanced")}
                <Accordion.Indicator />
              </Accordion.Trigger>
            </Accordion.Heading>
            <Accordion.Panel>
              <Accordion.Body>
                <ChannelAdvanced
                  fields={props.advancedFields}
                  savedSecrets={props.savedSecretFields}
                  presets={props.availablePresets}
                  presetLabel={props.setup.presetLabel}
                  onApplyPreset={props.onApplyPreset}
                  {...form}
                />
              </Accordion.Body>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      )}
      {mode === "credentials" && (
        <div className="channel-setup-actions">
          <Button
            type="submit"
            size="sm"
            variant="secondary"
            isDisabled={props.actionPending || props.autoSaving || !props.dirty}
            isPending={props.autoSaving}
          >
            {t("settings.channels.saveSettings")}
          </Button>
          {props.feature.setup?.verifies_connection && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              isDisabled={props.actionPending}
              isPending={props.validating}
              onPress={props.onCheckConnection}
            >
              {t("settings.channels.checkConnection")}
            </Button>
          )}
          <ToggleField
            label={t("settings.channels.enable")}
            selected={Boolean(
              props.feature.capabilities?.includes("always_enabled") ||
                props.enabled,
            )}
            disabled={
              props.actionPending ||
              props.feature.capabilities?.includes("always_enabled")
            }
            onChange={props.onToggleEnabled}
          />
        </div>
      )}
      {mode === "credentials" && (
        <ChannelValidationResult
          feature={props.feature}
          validation={props.validation}
          validating={props.validating}
        />
      )}
    </Form>
  );
}
