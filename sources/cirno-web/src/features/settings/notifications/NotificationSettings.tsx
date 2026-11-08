import { Card } from "@heroui/react";
import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import type { DisplayPreferences } from "@/features/preferences/store";
import { INBOX_CATEGORIES } from "@/features/inbox/model/store";
import { ToggleField } from "@/ui/fields/ToggleField";
import { BrowserNotificationSettings } from "./BrowserNotificationSettings";
import "./notifications.css";

export function NotificationSettings({ displayPreferences, onChangePreferences }: {
  displayPreferences: DisplayPreferences; onChangePreferences: Dispatch<SetStateAction<DisplayPreferences>>;
}) {
  const { t } = useTranslation();
  return <div className="notification-settings">
    <section><h2>{t("settings.notifications.scope")}</h2>
      <Card><Card.Content className="notification-options">
        <BrowserNotificationSettings displayPreferences={displayPreferences} onChangePreferences={onChangePreferences} />
        <ToggleField label={t("settings.rows.notificationSound")} description={t("settings.help.notificationSound")} selected={displayPreferences.notificationSound}
          onChange={notificationSound => onChangePreferences(previous => ({ ...previous, notificationSound }))} />
      </Card.Content></Card>
      <p className="notification-help">{t("settings.notifications.pageRequired")}</p>
    </section>
    <section><h2>{t("inbox.categories")}</h2>
      <Card><Card.Content className="notification-options">{INBOX_CATEGORIES.map(category =>
        <ToggleField key={category} label={t(`inbox.category.${category}`)} selected={!displayPreferences.mutedNotificationCategories?.includes(category)}
          onChange={enabled => onChangePreferences(previous => ({ ...previous,
            mutedNotificationCategories: enabled ? (previous.mutedNotificationCategories ?? []).filter(value => value !== category)
              : [...new Set([...(previous.mutedNotificationCategories ?? []), category])],
          }))} />
      )}</Card.Content></Card>
      <p className="notification-help">{t("inbox.muteHelp")}</p>
    </section>
  </div>;
}
