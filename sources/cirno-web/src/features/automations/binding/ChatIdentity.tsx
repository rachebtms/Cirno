import { useTranslation } from "react-i18next";
import {ChannelLogo} from "@/features/channels/ui/ChannelLogo";
import {
  channelUiOwner,
  channelUiPresentation,
} from "@/channel-plugins/registry";
import { channelTranslator } from "@/channel-plugins/i18n";
import type { AutomationChat } from "@/lib/contracts/automations";
import type { CirnoFeatureInfo } from "@/lib/contracts/channels";
export function ChatIdentity({
  chat,
  title,
  showBrandLogos,
}: {
  chat: AutomationChat;
  title: string;
  showBrandLogos: boolean;
}) {
  const { t } = useTranslation();
  const owner = channelUiOwner(chat.channel);
  const presentation = channelUiPresentation(chat.channel);
  const platform =
    chat.channel === "websocket"
      ? t("settings.automations.chat.web")
      : channelTranslator(t, owner)(
          "displayName",
          presentation?.displayName ?? chat.channel,
        );
  const feature: CirnoFeatureInfo = {
    name: chat.channel,
    display_name: platform,
    type: "channel",
    enabled: true,
    installed: true,
    ready: true,
    status: "ready",
    install_supported: false,
    requires_restart: false,
  };
  return (
    <span className="flex min-w-0 items-center gap-2.5 text-start">
      <span aria-hidden className="relative h-6 w-6 shrink-0">
        {chat.channel === "websocket" ? (
          <img
            src="/brand/cirno_snowflake_mark.svg"
            alt=""
            className="h-6 w-6"
          />
        ) : (
          <span className="absolute left-0 top-0 origin-top-left scale-75">
            <ChannelLogo feature={feature} showBrandLogos={showBrandLogos} />
          </span>
        )}
      </span>
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="break-words text-sm leading-5 [overflow-wrap:anywhere]">
          {title}
        </span>
        <span className="text-xs leading-4 text-muted-foreground">
          {platform}
        </span>
      </span>
    </span>
  );
}
