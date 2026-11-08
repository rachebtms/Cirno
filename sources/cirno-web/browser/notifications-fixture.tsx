import { useTranslation } from "react-i18next";
import { NotificationSettings } from "@/features/settings/notifications/NotificationSettings";
import { usePreferences } from "@/hooks/usePreferences";
import { useTheme } from "@/hooks/useTheme";
import { writePreferences } from "@/features/preferences/store";

export function NotificationsFixture() {
  useTheme();
  const { t } = useTranslation();
  const preferences = usePreferences();
  return <main className="min-h-screen bg-background p-4 text-foreground sm:p-8"><div className="mx-auto max-w-3xl">
    <h1 className="mb-6 text-xl font-semibold">{t("settings.nav.notifications")}</h1>
    <NotificationSettings displayPreferences={preferences} onChangePreferences={writePreferences} />
  </div></main>;
}
