import { Suspense, type ComponentType, type ReactNode } from "react";
import { Spinner } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type {
  ChannelPluginPanelProps,
  ChannelPluginConnectFlowProps,
} from "@/channel-plugins/types";
import type { ChannelSetupPresentation } from "@/channel-plugins/catalog";
import { copyTextToClipboard } from "@/lib/clipboard";
import { useChannelSetup } from "../../model/useChannelSetup";
import { ChannelSetupView } from "./ChannelSetupView";
export function ChannelSetupSurface({
  feature,
  setup,
  header,
  ConnectFlow,
  onFeaturesUpdate,
  onBeforeCloseChange,
  token,
  connectRequestId,
}: ChannelPluginPanelProps & {
  setup: ChannelSetupPresentation;
  header: ReactNode;
  ConnectFlow?: ComponentType<ChannelPluginConnectFlowProps>;
}) {
  const { t } = useTranslation(),
    state = useChannelSetup(
      feature,
      setup,
      onFeaturesUpdate,
      onBeforeCloseChange,
    );

  const { draft, actions, intent, layout, completion, advanced } = state;
  const manualBusy = intent.busy || (actions.mutation.busy && actions.kind !== "save");
  return (
    <div
      onChangeCapture={completion.onChangeCapture}
      onFocusCapture={completion.onFocusCapture}
      onBlurCapture={completion.onBlurCapture}
    >
      <ChannelSetupView
        header={header}
        feature={feature}
        setup={setup}
        primaryFields={layout.primary}
        advancedFields={layout.advanced}
        savedSecretFields={layout.editable.filter(
          (field) =>
            field.secret && feature.configured_fields?.includes(field.key),
        )}
        availablePresets={layout.presets}
        configuredFields={new Set(feature.configured_fields ?? [])}
        fieldValues={draft.values}
        visibleSecrets={draft.visible}
        clearedSecrets={draft.cleared}
        fieldErrors={actions.errors}
        actionPending={manualBusy}
        dirty={draft.dirty}
        enabled={intent.kind === "enable" || (intent.kind !== "disable" && actions.enabled)}
        autoSaving={actions.mutation.busy && actions.kind === "save"}
        autoSaveState={
          !draft.dirty &&
          actions.kind === "save" &&
          actions.feedback?.tone === "success"
            ? "saved"
            : "idle"
        }
        advancedOpen={advanced.open}
        validation={actions.validation}
        validating={
          actions.mutation.busy &&
          (actions.kind === "check" || actions.kind === "enable")
        }
        notice={
          intent.error ?? (actions.kind === "save" && actions.feedback?.tone === "success"
            ? null
            : (actions.feedback?.text ?? null))
        }
        noticeTone={intent.error ? "danger" : actions.feedback?.tone}
        onAdvancedOpenChange={(open) => {
          void advanced.change(open);
        }}
        onChangeField={(key, value) => {
          draft.change(key, value);
          actions.clearError(key);
        }}
        onToggleSecret={draft.toggleSecret}
        onClearSecret={(key, clear) => {
          completion.complete();
          draft.clearSecret(key, clear);
        }}
        onApplyPreset={(preset) => {
          completion.complete();
          draft.applyPreset(preset);
        }}
        onSubmit={() => {
          void completion.commit();
        }}
        onCheckConnection={() => {
          void intent.check();
        }}
        onToggleEnabled={(enabled) => {
          void intent.toggle(enabled);
        }}
        onCopyCommand={() => {
          if (setup.command)
            void copyTextToClipboard(setup.command).then((ok) =>
              actions.setFeedback(
                t(
                  ok
                    ? "settings.channels.commandCopied"
                    : "settings.channels.commandCopyFailed",
                ),
                ok ? "info" : "danger",
              ),
            );
        }}
        onNotice={(notice) => {
          if (notice) actions.setFeedback(notice);
        }}
        connectFlow={
          layout.mode === "connect" && ConnectFlow ? (
            <Suspense fallback={<Spinner size="sm" />}>
              <ConnectFlow
                token={token}
                feature={feature}
                idleLabel={
                  setup.primaryActionLabel ?? t("settings.channels.connect")
                }
                connectRequestId={connectRequestId}
                onOpenAdvanced={() => {
                  void advanced.change(true);
                }}
                onFeaturesUpdate={onFeaturesUpdate}
              />
            </Suspense>
          ) : undefined
        }
      />
    </div>
  );
}
