import { Button, Popover } from "@heroui/react";
import { CircleHelp, ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { channelUiContribution } from "@/channel-plugins/registry";
import { docsUrlWithBase } from "@/channel-plugins/catalog";
import { channelSetup } from "@/features/channels/model/presentation";
import type { CirnoFeatureInfo } from "@/lib/contracts/channels";
export function ChannelHelp({
  feature,
  chatAppsDocsUrl,
}: {
  feature: CirnoFeatureInfo;
  chatAppsDocsUrl?: string;
}) {
  const { t, i18n } = useTranslation(),
    setup = channelSetup(feature, i18n.resolvedLanguage ?? i18n.language);
  const links = [
    { url: setup.officialUrl, label: setup.officialLabel },
    {
      url: docsUrlWithBase(setup.docsUrl, chatAppsDocsUrl),
      label: setup.docsLabel,
    },
  ].filter((link) => link.url);
  const Help = channelUiContribution(feature.name, feature.webui)?.HelpContent;
  if (!links.length && !Help) return null;
  return (
    <Popover>
      <Button
        variant="ghost"
        size="sm"
        isIconOnly
        aria-label={t("settings.channels.help")}
      >
        <CircleHelp size={18} />
      </Button>
      <Popover.Content placement="bottom end">
        <Popover.Dialog
          aria-label={t("settings.channels.help")}
          className="channel-help"
        >
          {Help && <Help feature={feature} />}
          {links.map((link) => (
            <a key={link.url} href={link.url} target="_blank" rel="noreferrer">
              {link.label ?? t("settings.channels.help")}
              <ExternalLink size={14} />
            </a>
          ))}
        </Popover.Dialog>
      </Popover.Content>
    </Popover>
  );
}
