import { Avatar } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type {
  CirnoChannelInstanceInfo,
  CirnoFeatureInfo,
} from "@/lib/contracts/channels";
import { channelStatusLabel } from "../../model/status";
import { ChannelLogo } from "../ChannelLogo";
export function channelInstanceName(instance: CirnoChannelInstanceInfo) {
  return instance.display_name?.trim() || instance.name.trim() || instance.id;
}
export function ChannelInstanceIdentity({
  feature,
  instance,
  showBrandLogos,
}: {
  feature: CirnoFeatureInfo;
  instance: CirnoChannelInstanceInfo;
  showBrandLogos: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="channel-instance-identity">
      <Avatar aria-hidden="true">
        {instance.avatar_url && (
          <Avatar.Image src={instance.avatar_url} alt="" loading="lazy" />
        )}
        <Avatar.Fallback>
          <ChannelLogo feature={feature} showBrandLogos={showBrandLogos} />
        </Avatar.Fallback>
      </Avatar>
      <div>
        <h4>{channelInstanceName(instance)}</h4>
        <span>
          {channelStatusLabel({ ...feature, ...instance }, (key, fallback) =>
            t(key, { defaultValue: fallback }),
          )}
        </span>
      </div>
    </div>
  );
}
