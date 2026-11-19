import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AccountRequestError, accountRequest, accountStatus, validAccountPassword, type AccountStatus } from "@/lib/account";
import { useMutation } from "@/ui/resources/useMutation";

const emptyPasswords = { current: "", next: "", confirm: "" };

export function useAccountSettings() {
  const { t } = useTranslation();
  const [account, setAccountState] = useState<AccountStatus | null>(null);
  const accountWrite = useRef(0);
  const setAccount = useCallback((value: AccountStatus) => {
    accountWrite.current += 1;
    setAccountState(value);
  }, []);
  const owner = useRef({}).current;
  const mutation = useMutation(owner);
  const [passwords, setPasswords] = useState(emptyPasswords);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let disposed = false;
    const startedAtWrite = accountWrite.current;
    const message = (reason: unknown) => reason instanceof AccountRequestError
      ? t(`setup.errors.${reason.code}`, { defaultValue: t("setup.errors.request_failed") })
      : t("setup.errors.connection_failed");
    void accountStatus().then(value => {
      if (!disposed && startedAtWrite === accountWrite.current) setAccountState(value);
    }).catch(reason => {
      if (!disposed && startedAtWrite === accountWrite.current) setLoadError(message(reason));
    });
    return () => { disposed = true; };
  }, [revision, t]);
  const change = (key: keyof typeof passwords, value: string) => {
    setPasswords(current => ({ ...current, [key]: value }));
    setSaved(false);
    setError("");
    mutation.clear();
  };
  const submit = async () => {
    setError("");
    setSaved(false);
    if (!validAccountPassword(passwords.next)) { setError(t("setup.errors.invalid_password")); return; }
    if (passwords.next !== passwords.confirm) { setError(t("setup.errors.password_mismatch")); return; }
    await mutation.run(async () => {
      try {
        await accountRequest("change-password", { current_password: passwords.current, new_password: passwords.next });
      } catch (reason) {
        throw new Error(reason instanceof AccountRequestError
          ? t(`setup.errors.${reason.code}`, { defaultValue: t("setup.errors.request_failed") })
          : t("setup.errors.connection_failed"), { cause: reason });
      }
    }, () => {
      setPasswords(emptyPasswords);
      setSaved(true);
    });
  };
  return { account, setAccount, passwords, busy: mutation.busy, error: error || mutation.error || "", loadError, saved, change, submit,
    retry: () => { setLoadError(""); setRevision(value => value + 1); } };
}
