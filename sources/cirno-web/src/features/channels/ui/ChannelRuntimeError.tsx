import { useTranslation } from "react-i18next";
import { InlineError } from "@/ui/feedback/InlineError";
import { channelValidationMessage } from "../model/validationMessages";
export function ChannelRuntimeError({
  message,
  className = "",
}: {
  message?: string;
  className?: string;
}) {
  const { t } = useTranslation();
  return message ? (
    <div className={className}>
      <InlineError message={channelValidationMessage(message, t)} />
    </div>
  ) : null;
}
