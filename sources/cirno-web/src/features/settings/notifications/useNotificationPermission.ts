import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import { enableBrowserNotifications, lastNotificationProblem, NOTIFICATION_STATUS_EVENT, notificationProblem, notificationWorkerProblem, showBrowserNotification, type NotificationResult } from "@/lib/browser-notifications";
import type { DisplayPreferences } from "@/features/preferences/store";

export function useNotificationPermission(displayPreferences: DisplayPreferences, onChangePreferences: Dispatch<SetStateAction<DisplayPreferences>>) {
  const { t } = useTranslation();
  const [problem, setProblem] = useState(notificationProblem);
  const [workerProblem, setWorkerProblem] = useState<"workerUnavailable" | null>(null);
  const [feedback, setFeedback] = useState<NotificationResult | null>(lastNotificationProblem);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const operation = useRef(0);
  const workerCheck = useRef(0);
  const refreshRef = useRef(() => {});

  useEffect(() => {
    const refresh = () => {
      const next = notificationProblem();
      setProblem(next);
      const id = ++workerCheck.current;
      setChecking(!next);
      if (!next) {
        void notificationWorkerProblem().then((value) => {
          if (id === workerCheck.current) {
            setWorkerProblem(value);
            setChecking(false);
          }
        });
      }
    };
    refreshRef.current = refresh;
    const deliveryStatus = () => { setFeedback(lastNotificationProblem()); refresh(); };
    refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener(NOTIFICATION_STATUS_EVENT, deliveryStatus);
    document.addEventListener("visibilitychange", refresh);
    navigator.serviceWorker?.addEventListener("controllerchange", refresh);
    return () => {
      workerCheck.current++;
      window.removeEventListener("focus", refresh);
      window.removeEventListener(NOTIFICATION_STATUS_EVENT, deliveryStatus);
      document.removeEventListener("visibilitychange", refresh);
      navigator.serviceWorker?.removeEventListener("controllerchange", refresh);
    };
  }, []);
  useEffect(() => () => { operation.current++; }, []);

  const granted = typeof Notification !== "undefined" && Notification.permission === "granted";
  const enabled = displayPreferences.browserNotifications && granted;
  const revoked = feedback === "revoked" && typeof Notification !== "undefined" && !granted;
  const detail = revoked ? "revoked" : problem || (feedback === "revoked" ? null : feedback) || workerProblem;
  const message = busy || checking ? t("settings.notifications.waiting")
    : detail && detail !== "skipped" ? t(`settings.notifications.${detail}`) : null;
  const canRetry = !!(problem || workerProblem || revoked || feedback === "workerUnavailable");

  async function toggle(value: boolean) {
    const id = ++operation.current;
    setFeedback(null);
    if (!value) {
      onChangePreferences((previous) => ({ ...previous, browserNotifications: false }));
      return;
    }
    setBusy(true);
    const result = await enableBrowserNotifications();
    if (id !== operation.current) return;
    setBusy(false);
    setProblem(notificationProblem());
    setWorkerProblem(result === "workerUnavailable" ? result : null);
    setFeedback(result);
    if (!result) {
      onChangePreferences((previous) => ({ ...previous, browserNotifications: true }));
    }
  }
  async function test() {
    const id = ++operation.current;
    setBusy(true);
    const result = await showBrowserNotification(t("settings.notifications.testBody"), {
      key: `test:${crypto.randomUUID()}`, url: `${window.location.origin}/#/settings?section=notifications`, test: true,
    });
    if (id !== operation.current) return;
    setBusy(false);
    setProblem(notificationProblem());
    setFeedback(lastNotificationProblem() ?? result);
  }
  return { enabled, message, canRetry, busy, checking, toggle, test,
    disabled: busy || (!!problem && !displayPreferences.browserNotifications),
    testDisabled: busy || checking || !!problem || !!workerProblem,
    retry: () => { setFeedback(null); refreshRef.current(); } };
}
