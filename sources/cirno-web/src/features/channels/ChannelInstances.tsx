import { Button, Card } from "@heroui/react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ChannelPluginPanelProps } from "@/channel-plugins/types";
import { ToggleField } from "@/ui/fields/ToggleField";
import { InlineError } from "@/ui/feedback/InlineError";
import {
  channelSetup,
  localizedChannelDisplayName,
} from "./model/presentation";
import { channelToggleChecked } from "./model/status";
import { useChannelInstances } from "./model/useChannelInstances";
import { ChannelLogo } from "./ui/ChannelLogo";
import { ChannelRuntimeError } from "./ui/ChannelRuntimeError";
import { ChannelInstanceEditor } from "./ui/instances/ChannelInstanceEditor";
import {
  ChannelInstanceIdentity,
  channelInstanceName,
} from "./ui/instances/ChannelInstanceIdentity";
export function ChannelInstances({
  feature,
  showBrandLogos,
  onFeaturesUpdate,
  onBeforeCloseChange,
}: Pick<
  ChannelPluginPanelProps,
  "feature" | "showBrandLogos" | "onFeaturesUpdate" | "onBeforeCloseChange"
>) {
  const { t, i18n } = useTranslation(),
    state = useChannelInstances(feature, onFeaturesUpdate, onBeforeCloseChange);
  const setup = channelSetup(feature, i18n.resolvedLanguage ?? i18n.language),
    fields = [
      ...new Map(
        [...(setup.fields ?? []), ...(setup.manualFields ?? [])].map(
          (field) => [field.key, field],
        ),
      ).values(),
    ];
  return (
    <div className="channel-instances">
      <div className="channel-setup-identity">
        <ChannelLogo feature={feature} showBrandLogos={showBrandLogos} />
        <h3>{localizedChannelDisplayName(feature, t)}</h3>
      </div>
      <ChannelRuntimeError message={feature.runtime_error} />
      <InlineError
        message={state.mutation.error ?? state.selection.mutation.error}
      />
      {(feature.instances ?? []).map((instance) => {
        const expanded = state.selection.selected?.name === instance.id,
          pending =
            state.operation?.id === instance.id &&
            state.operation.kind === "toggle";
        return (
          <article key={instance.id}>
            <Card>
              <Card.Content>
                <div className="channel-instance-heading">
                  <ChannelInstanceIdentity
                    feature={feature}
                    instance={instance}
                    showBrandLogos={showBrandLogos}
                  />
                  <div className="channel-instance-actions">
                    {fields.length > 0 && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        aria-expanded={expanded}
                        isDisabled={
                          state.mutation.busy || state.selection.mutation.busy
                        }
                        onPress={() => {
                          void state.edit(instance.id);
                        }}
                      >
                        {t("settings.channels.advanced")}
                        <ChevronDown size={16} />
                      </Button>
                    )}
                    <ToggleField
                      labelHidden
                      label={t("settings.channels.toggleInstance", {
                        name: channelInstanceName(instance),
                      })}
                      selected={Boolean(
                        pending
                          ? state.operation?.checked
                          : channelToggleChecked(instance),
                      )}
                      disabled={
                        state.mutation.busy ||
                        state.selection.mutation.busy ||
                        !instance.configured
                      }
                      onChange={(checked) => {
                        void state.toggle(instance, checked);
                      }}
                    />
                  </div>
                </div>
                <ChannelRuntimeError message={instance.runtime_error} />
                {expanded && fields.length > 0 && (
                  <ChannelInstanceEditor
                    key={instance.id}
                    state={state}
                    instance={instance}
                    fields={fields}
                  />
                )}
              </Card.Content>
            </Card>
          </article>
        );
      })}
      {!feature.instances?.length && (
        <p className="channel-setup-hint">
          {t("settings.channels.configuredInstances", { count: 0 })}
        </p>
      )}
    </div>
  );
}
