import { Button } from "@heroui/react";
import { BellRing } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import type { DisplayPreferences } from "@/features/preferences/store";
import { ToggleField } from "@/ui/fields/ToggleField";
import { Hint } from "@/ui/feedback/Hint";
import { useNotificationPermission } from "./useNotificationPermission";
import "./notifications.css";

export function BrowserNotificationSettings({ displayPreferences, onChangePreferences }: {
  displayPreferences: DisplayPreferences; onChangePreferences: Dispatch<SetStateAction<DisplayPreferences>>;
}) {
  const { t } = useTranslation();
  const permission = useNotificationPermission(displayPreferences, onChangePreferences);
  return <div className="notification-permission">
    <div className="notification-permission-row">
      <ToggleField label={t("settings.rows.browserNotifications")} selected={permission.enabled} disabled={permission.disabled}
        onChange={value => { void permission.toggle(value); }} description={<>
          <span>{t("settings.help.browserNotifications")}</span>
          <span className="notification-status" role="status" aria-live="polite" aria-atomic="true">{permission.message}</span>
        </>} />
      {permission.enabled && <Hint content={t("settings.notifications.test")}>
        <Button isIconOnly variant="ghost" aria-label={t("settings.notifications.test")} isDisabled={permission.testDisabled} isPending={permission.busy}
          onPress={() => { void permission.test(); }}><BellRing size={18} /></Button>
      </Hint>}
    </div>
    {permission.canRetry && <Button size="sm" variant="secondary" isDisabled={permission.busy || permission.checking} onPress={permission.retry}>{t("settings.notifications.retry")}</Button>}
  </div>;
}
