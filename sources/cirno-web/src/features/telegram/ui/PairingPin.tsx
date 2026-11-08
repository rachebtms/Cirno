import { Button } from "@heroui/react";
import { Check, Copy, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { TelegramPin } from "@/lib/contracts/telegram";
import { copyTextToClipboard } from "@/lib/clipboard";
import { InlineError } from "@/ui/feedback/InlineError";
import { usePinClock } from "../model/usePinClock";
export function PairingPin({
  pin,
  busy,
  onRefresh,
  onCancel,
}: {
  pin: TelegramPin;
  busy: boolean;
  onRefresh: () => unknown;
  onCancel: () => unknown;
}) {
  const { t } = useTranslation(),
    seconds = usePinClock(pin.expires_at);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">(
    "idle",
  );
  const command = `/bind ${pin.pin}`;
  const copy = async () =>
    setCopyState((await copyTextToClipboard(command)) ? "copied" : "error");
  return (
    <div className="telegram-pairing-pin">
      <div className="telegram-pin-row">
        <code
          aria-label={t("settings.telegram.pin")}
          data-expired={seconds === 0}
        >
          {pin.pin}
        </code>
        <div className="telegram-actions">
          <Button
            variant="ghost"
            size="sm"
            isIconOnly
            isDisabled={busy || !seconds}
            aria-label={t("settings.telegram.copyPin")}
            onPress={() => {
              void copy();
            }}
          >
            {copyState === "copied" ? <Check size={17} /> : <Copy size={17} />}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            isIconOnly
            isPending={busy}
            aria-label={t("settings.telegram.refreshPin")}
            onPress={() => {
              void onRefresh();
            }}
          >
            <RefreshCw size={17} />
          </Button>
        </div>
      </div>
      <p className="telegram-hint">
        {seconds
          ? t("settings.telegram.expires", { seconds })
          : t("settings.telegram.expired")}
      </p>
      <p className="telegram-hint">
        {t("settings.telegram.sendPin", { command })}
      </p>
      <InlineError
        message={copyState === "error" ? t("common.copyFailed") : null}
      />
      <Button
        variant="ghost"
        size="sm"
        isDisabled={busy}
        onPress={() => {
          void onCancel();
        }}
      >
        {t("common.cancel")}
      </Button>
    </div>
  );
}
