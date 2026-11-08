import { Button, Card } from "@heroui/react";
import { Link2, Unlink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { InlineError } from "@/ui/feedback/InlineError";
import { SkeletonStatus } from "@/ui/feedback/SkeletonStatus";
import type { TelegramBindingState } from "../model/useTelegramBinding";
import type { TelegramPairingState } from "../model/useTelegramPairing";
import { PairingPin } from "./PairingPin";
export function TelegramAccount({
  binding,
  pairing,
  onConfigure,
}: {
  binding: TelegramBindingState;
  pairing: TelegramPairingState;
  onConfigure: () => void;
}) {
  const { t } = useTranslation(),
    data = binding.status.value;
  const busy = binding.mutation.busy || pairing.operation.busy;
  return (
    <section className="telegram-section">
      <header className="telegram-section-heading">
        <h2>{t("settings.telegram.account")}</h2>
        <Button variant="ghost" size="sm" onPress={onConfigure}>
          {t("settings.telegram.configureBot")}
        </Button>
      </header>
      <p className="telegram-hint">{t("settings.telegram.help")}</p>
      <Card>
        <Card.Content className="telegram-account-content">
          {!data && !binding.status.error && (
            <SkeletonStatus
              label={t("settings.loading")}
              className="telegram-skeleton"
            >
              <span />
              <span />
            </SkeletonStatus>
          )}
          <InlineError message={binding.status.error} />
          {binding.status.error && (
            <Button
              variant="secondary"
              size="sm"
              isDisabled={busy}
              onPress={pairing.retryStatus}
            >
              {t("common.retry")}
            </Button>
          )}
          {data && (
            <>
              <div className="telegram-account-summary">
                <div>
                  <h3>
                    {data.bound
                      ? data.username
                        ? `@${data.username}`
                        : data.user_id
                      : t("settings.telegram.unbound")}
                  </h3>
                  <p className="telegram-hint">
                    {t(
                      data.bound
                        ? "settings.telegram.boundHelp"
                        : "settings.telegram.pinHelp",
                    )}
                  </p>
                </div>
                {(data.bound || !pairing.pin) && (
                  <Button
                    variant={data.bound ? "secondary" : "primary"}
                    size="sm"
                    isDisabled={busy}
                    isPending={busy && !pairing.pin}
                    onPress={() => {
                      void (data.bound
                        ? pairing.disconnect()
                        : pairing.issue());
                    }}
                  >
                    {data.bound ? <Unlink size={16} /> : <Link2 size={16} />}
                    {t(
                      data.bound
                        ? "settings.telegram.unbind"
                        : "settings.telegram.generatePin",
                    )}
                  </Button>
                )}
              </div>
              {pairing.pin && !data.bound && (
                <PairingPin
                  key={pairing.pin.pin}
                  pin={pairing.pin}
                  busy={busy}
                  onRefresh={pairing.issue}
                  onCancel={pairing.disconnect}
                />
              )}
            </>
          )}
          <InlineError message={pairing.operation.error} />
          <InlineError message={binding.errorFor("account")} />
        </Card.Content>
      </Card>
    </section>
  );
}
