import { Card } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { TelegramBinding } from "@/lib/contracts/telegram";
import { ToggleField } from "@/ui/fields/ToggleField";
import { InlineError } from "@/ui/feedback/InlineError";
import type { TelegramBindingState } from "../model/useTelegramBinding";
const categories = ["router", "operations", "conversations", "system"] as const;
export function TelegramDelivery({
  data,
  state,
}: {
  data: TelegramBinding;
  state: TelegramBindingState;
}) {
  const { t } = useTranslation();
  return (
    <section className="telegram-section">
      <h2>{t("settings.telegram.delivery")}</h2>
      <Card>
        <Card.Content className="telegram-delivery-options">
          <ToggleField
            label={t("settings.telegram.enabled")}
            selected={data.enabled}
            disabled={state.mutation.busy}
            onChange={(enabled) => {
              void state.update({ enabled }, "delivery");
            }}
          />
          {categories.map((category) => (
            <ToggleField
              key={category}
              label={t(
                category === "router"
                  ? "settings.telegram.router"
                  : `inbox.category.${category}`,
              )}
              selected={data.notifications.includes(category)}
              disabled={state.mutation.busy || !data.enabled}
              onChange={(enabled) => {
                void state.update(
                  {
                    notifications: enabled
                      ? [...data.notifications, category]
                      : data.notifications.filter(
                          (value) => value !== category,
                        ),
                  },
                  "delivery",
                );
              }}
            />
          ))}
          <InlineError message={state.errorFor("delivery")} />
        </Card.Content>
      </Card>
    </section>
  );
}
