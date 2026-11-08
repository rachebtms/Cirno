import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation } from "@/ui/resources/useMutation";
import { useRequest } from "@/ui/resources/useRequest";
import type { ChannelSetupPresentation } from "@/channel-plugins/catalog";
import type {
  ChannelConfigurePayload,
  ChannelValidationPayload,
  CirnoFeatureInfo,
  CirnoFeaturesPayload,
} from "@/lib/contracts/channels";
import { channelToggleChecked } from "@/features/channels/model/status";
import { channelValidationMessage } from "@/features/channels/model/validationMessages";
import {
  channelRequirementErrors,
  channelServerValidationErrors,
  focusFirstChannelFieldError,
} from "./fieldValidation";
import type { ChannelSetupService } from "./setupService";
import type { ChannelDraft } from "./useChannelDraft";
import type { ChannelSetupLayout } from "./setupLayout";
export interface ChannelFeedback {
  text: string;
  tone: "danger" | "success" | "info";
}
type Kind = "save" | "check" | "enable" | "disable";
export function useChannelActions(
  service: ChannelSetupService,
  feature: CirnoFeatureInfo,
  setup: ChannelSetupPresentation,
  layout: ChannelSetupLayout,
  draft: ChannelDraft,
  onFeaturesUpdate: (payload: CirnoFeaturesPayload) => void,
  onAdvanced: () => void,
) {
  const { t } = useTranslation(),
    mutation = useMutation(service),
    validation = useRequest<ChannelValidationPayload>(service);
  const [local, setLocal] = useState({
    service,
    kind: null as Kind | null,
    feedback: null as ChannelFeedback | null,
    errors: {} as Record<string, string>,
  });
  const current =
    local.service === service
      ? local
      : { service, kind: null, feedback: null, errors: {} };
  const feedback = (text: string, tone: ChannelFeedback["tone"] = "info") => {
    if (validation.isCurrent())
      setLocal((previous) => ({
        ...previous,
        service,
        feedback: { text, tone },
      }));
  };
  const setErrors = (errors: Record<string, string>) =>
    setLocal((previous) => ({ ...previous, service, errors }));
  const begin = (kind: Kind) => {
    setLocal({ service, kind, feedback: null, errors: {} });
    if (kind !== "save") validation.clear();
  };
  const acknowledge = (
    payload: ChannelConfigurePayload,
    snapshot: ChannelDraft["snapshot"],
  ) => {
    draft.ack(snapshot);
    if (payload.cirno_features) onFeaturesUpdate(payload.cirno_features);
  };
  const showValidation = (result: ChannelValidationPayload) => {
    validation.assign(result);
    const errors = channelServerValidationErrors(
      layout.fields,
      result.missing_fields,
      t("settings.channels.fieldRequired"),
    );
    setErrors(errors);
    if (layout.advanced.some((field) => errors[field.key])) onAdvanced();
    focusFirstChannelFieldError(errors, validation.isCurrent);
    const failed = result.checks.find((check) => check.status === "fail"),
      message = failed?.message ?? result.message;
    if (result.status !== "connected" && message)
      feedback(
        channelValidationMessage(message, t),
        result.can_enable ? "info" : "danger",
      );
  };
  return {
    mutation,
    isCurrent: validation.isCurrent,
    validation: validation.value,
    kind: current.kind,
    errors: current.errors,
    feedback: mutation.error
      ? { text: mutation.error, tone: "danger" as const }
      : current.feedback,
    enabled:
      mutation.busy && current.kind === "enable"
        ? true
        : mutation.busy && current.kind === "disable"
          ? false
          : channelToggleChecked(feature),
    setFeedback: feedback,
    clearError: (key: string) =>
      setLocal((previous) => {
        if (previous.service !== service) return previous;
        const errors = { ...previous.errors };
        delete errors[key];
        return { ...previous, errors };
      }),
    save: async () => {
      if (!validation.isCurrent()) return false;
      if (!draft.dirty) return true;
      const snapshot = draft.snapshot;
      return Boolean(
        await mutation.run(
          async () => {
            begin("save");
            return service.configure(draft.payload);
          },
          (payload) => {
            acknowledge(payload, snapshot);
            feedback(t("settings.channels.savedSettings"), "success");
          },
        ),
      );
    },
    check: () =>
      mutation.run(async () => {
        begin("check");
        return service.validate(draft.payload);
      }, showValidation),
    toggle: (enabled: boolean) => {
      if (!enabled)
        return mutation.run(async () => {
          begin("disable");
          return service.disable();
        }, onFeaturesUpdate);
      const errors = channelRequirementErrors(
        layout.fields,
        setup.requirements ?? [],
        draft.values,
        new Set(feature.configured_fields ?? []),
        draft.cleared,
        t("settings.channels.fieldRequired"),
      );
      if (Object.keys(errors).length) {
        setErrors(errors);
        if (layout.advanced.some((field) => errors[field.key])) onAdvanced();
        feedback(t("settings.channels.validationFailed"), "danger");
        focusFirstChannelFieldError(errors, validation.isCurrent);
        return;
      }
      const snapshot = draft.snapshot;
      return mutation.run(
        async () => {
          begin("enable");
          const result = await service.validate(draft.payload);
          const payload =
            result.can_enable && validation.isCurrent()
              ? await service.configure(draft.payload, true)
              : null;
          return { result, payload };
        },
        ({ result, payload }) => {
          showValidation(result);
          if (payload) {
            acknowledge(payload, snapshot);
            feedback(t("settings.channels.checkedAndEnabled"), "success");
          }
        },
      );
    },
  };
}
export type ChannelActions = ReturnType<typeof useChannelActions>;
