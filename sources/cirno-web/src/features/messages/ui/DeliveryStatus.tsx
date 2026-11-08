import { Button } from "@heroui/react";
import { CircleAlert, Clock3 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Hint } from "@/ui/feedback/Hint";
import { DetailsPopover } from "@/ui/overlays/DetailsPopover";
import type {
  MessageDeliveryErrorKind,
  MessageDeliveryStatus,
} from "@/lib/contracts/messages";
import { deliveryErrorCopy } from "../model/deliveryError";

export function DeliveryStatus({
  status,
  errorKind,
}: {
  status?: MessageDeliveryStatus;
  errorKind?: MessageDeliveryErrorKind;
}) {
  const { t } = useTranslation();
  if (status === "sending")
    return (
      <span role="status" className="message-delivery">
        <Clock3 size={14} aria-hidden />
        {t("message.delivery.sending")}
      </span>
    );
  if (status !== "failed") return null;
  const label = t("message.delivery.failed"),
    { title, body } = deliveryErrorCopy(errorKind, t);
  return (
    <div className="message-delivery">
      <DetailsPopover
        title={title}
        className="message-metadata-popover"
        trigger={
          <Hint
            content={
              <>
                <strong>{title}</strong>
                <p>{body}</p>
              </>
            }
            contentClassName="message-metadata-popover"
          >
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-label={`${label}: ${title}`}
              className="message-delivery-failed text-destructive/80 dark:text-red-400/80"
            >
              <CircleAlert size={14} aria-hidden />
              {label}
            </Button>
          </Hint>
        }
      >
        <p>{body}</p>
      </DetailsPopover>
      <span role="alert" className="sr-only">
        {title}. {body}
      </span>
    </div>
  );
}
