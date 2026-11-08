import { CircleAlert, CircleDot } from "lucide-react";
import { LoadingRing } from "@/components/ui/loading-ring";
import { useTranslation } from "react-i18next";

const icons = { running: LoadingRing, recovery: CircleAlert, updated: CircleDot };
export function ConversationStatus({ state, id }: { state: keyof typeof icons; id: string }) {
  const { t } = useTranslation();
  const Icon = icons[state];
  const label = t(`chat.activity.${state}`);
  return <span id={id} role="img" aria-label={label} className="conversation-status" data-state={state}><Icon width={15} height={15} aria-hidden /></span>;
}
