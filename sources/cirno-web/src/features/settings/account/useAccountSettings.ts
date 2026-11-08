import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AccountRequestError, accountRequest, accountStatus, validAccountPassword, type AccountStatus } from "@/lib/account";

const emptyPasswords = { current: "", next: "", confirm: "" };

export function useAccountSettings() {
  const { t } = useTranslation();
  const [account, setAccount] = useState<AccountStatus | null>(null);
  const [passwords, setPasswords] = useState(emptyPasswords);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let disposed = false;
    const message = (reason: unknown) => reason instanceof AccountRequestError
      ? t(`setup.errors.${reason.code}`, { defaultValue: t("setup.errors.request_failed") })
      : t("setup.errors.connection_failed");
    void accountStatus().then(value => { if (!disposed) setAccount(value); })
      .catch(reason => { if (!disposed) setLoadError(message(reason)); });
    return () => { disposed = true; };
  }, [revision, t]);
  const change = (key: keyof typeof passwords, value: string) => {
    setPasswords(current => ({ ...current, [key]: value }));
    setSaved(false);
    setError("");
  };
  const submit = async () => {
    setError("");
    setSaved(false);
    if (!validAccountPassword(passwords.next)) { setError(t("setup.errors.invalid_password")); return; }
    if (passwords.next !== passwords.confirm) { setError(t("setup.errors.password_mismatch")); return; }
    setBusy(true);
    try {
      await accountRequest("change-password", { current_password: passwords.current, new_password: passwords.next });
      setPasswords(emptyPasswords);
      setSaved(true);
    } catch (reason) {
      setError(reason instanceof AccountRequestError
        ? t(`setup.errors.${reason.code}`, { defaultValue: t("setup.errors.request_failed") })
        : t("setup.errors.connection_failed"));
    } finally {
      setBusy(false);
    }
  };
  return { account, setAccount, passwords, busy, error, loadError, saved, change, submit,
    retry: () => { setLoadError(""); setRevision(value => value + 1); } };
}
