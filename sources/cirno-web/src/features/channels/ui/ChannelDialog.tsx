import { Modal } from "@heroui/react";
import { useTranslation } from "react-i18next";
import { InlineError } from "@/ui/feedback/InlineError";
import { ChannelSetupPanel } from "@/features/channels/ChannelSetupPanel";
import type { CirnoFeatureInfo } from "@/lib/contracts/channels";
import type { ChannelsSettingsProps } from "../model/contracts";
import type { useChannelSelection } from "../model/useChannelSelection";
import { ChannelHelp } from "./ChannelHelp";
export function ChannelDialog({
  feature,
  state,
  settings,
}: {
  feature: CirnoFeatureInfo;
  state: ReturnType<typeof useChannelSelection>;
  settings: ChannelsSettingsProps;
}) {
  const { t } = useTranslation(),
    busy = state.mutation.busy;
  return (
    <Modal.Backdrop
      isOpen
      isDismissable={!busy}
      isKeyboardDismissDisabled={busy}
      onOpenChange={(open) => {
        if (!open) void state.close();
      }}
    >
      <Modal.Container size="lg">
        <Modal.Dialog className="channel-dialog">
          <Modal.Header className="channel-dialog-heading">
            <Modal.Heading>{t("settings.nav.channels")}</Modal.Heading>
            <div className="channel-dialog-controls">
              <ChannelHelp
                feature={feature}
                chatAppsDocsUrl={settings.chatAppsDocsUrl}
              />
              <Modal.CloseTrigger
                isDisabled={busy}
                aria-label={t("common.close")}
              />
            </div>
          </Modal.Header>
          <Modal.Body>
            <InlineError message={settings.error} />
            <InlineError message={state.mutation.error} />
            <ChannelSetupPanel
              key={feature.name}
              token={settings.token}
              feature={feature}
              actionKey={settings.actionKey}
              showBrandLogos={settings.showBrandLogos}
              onAction={settings.onAction}
              onFeaturesUpdate={settings.onFeaturesUpdate}
              connectRequestId={state.selected?.connect}
              onConfigureMcp={settings.onConfigureMcp}
              onBeforeCloseChange={state.setCompletion}
            />
          </Modal.Body>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
