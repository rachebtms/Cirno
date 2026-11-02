import { useEffect, useState, type FormEvent } from "react";
import { Eye, EyeOff, KeyRound, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SettingsGroup, SettingsRow, SettingsSectionTitle } from "@/components/settings/shared/SettingsControls";
import { AccountRequestError, accountRequest, accountStatus, validAccountPassword, type AccountStatus } from "@/lib/account";

export function AccountSettings() {
  const { t } = useTranslation();
  const [account, setAccount] = useState<AccountStatus | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [reload, setReload] = useState(0);

  const errorMessage = (reason: unknown) => reason instanceof AccountRequestError
    ? t(`setup.errors.${reason.code}`, { defaultValue: t("setup.errors.request_failed") })
    : t("setup.errors.connection_failed");

  useEffect(() => {
    let disposed = false;
    void accountStatus().then(value => { if (!disposed) setAccount(value); })
      .catch(reason => {
        if (!disposed) setError(reason instanceof AccountRequestError
          ? t(`setup.errors.${reason.code}`, { defaultValue: t("setup.errors.request_failed") })
          : t("setup.errors.connection_failed"));
      });
    return () => { disposed = true; };
  }, [reload, t]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSaved(false);
    if (!validAccountPassword(newPassword)) { setError(t("setup.errors.invalid_password")); return; }
    if (newPassword !== confirmPassword) { setError(t("setup.errors.password_mismatch")); return; }
    setBusy(true);
    try {
      await accountRequest("change-password", { current_password: currentPassword, new_password: newPassword });
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      setSaved(true);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return <div className="settings-stack">
    {error && <p role="alert" className="break-words text-sm leading-6 text-destructive">{error}</p>}
    {!account ? <div className="flex items-center gap-3 text-sm text-muted-foreground">
      {error ? <Button variant="secondary" onClick={() => { setError(""); setReload(value => value + 1); }}>{t("settings.account.retry")}</Button>
        : <><Loader2 className="h-4 w-4 animate-spin" aria-hidden />{t("settings.account.loading")}</>}
    </div> : !account.enabled || !account.authenticated ? <p className="text-sm leading-6 text-muted-foreground">{t("settings.account.unavailable")}</p> : <>
      <section><SettingsSectionTitle>{t("settings.account.owner")}</SettingsSectionTitle>
        <SettingsGroup><SettingsRow inline title={t("setup.username")}><span className="break-all text-sm text-muted-foreground">{account.username}</span></SettingsRow></SettingsGroup>
      </section>
      <section><SettingsSectionTitle>{t("settings.account.changePassword")}</SettingsSectionTitle>
        <SettingsGroup><form onSubmit={event => { void submit(event); }} className="space-y-5 p-4 sm:p-6">
          <div className="flex items-start gap-3 text-sm leading-6 text-muted-foreground"><KeyRound className="mt-1 h-4 w-4 shrink-0" aria-hidden /><p>{t("settings.account.help")}</p></div>
          <input type="text" name="username" autoComplete="username" value={account.username ?? ""} readOnly hidden />
          {([
            ["current", "settings.account.currentPassword", currentPassword, setCurrentPassword, "current-password"],
            ["new", "settings.account.newPassword", newPassword, setNewPassword, "new-password"],
            ["confirm", "setup.confirmPassword", confirmPassword, setConfirmPassword, "new-password"],
          ] as const).map(([id, label, value, change, autoComplete]) => <div key={id} className="space-y-2">
            <label htmlFor={`account-change-${id}`} className="block text-sm font-medium">{t(label)}</label><Input id={`account-change-${id}`} name={`${id}Password`} type={visible ? "text" : "password"} autoComplete={autoComplete}
              value={value} onChange={event => { change(event.target.value); setSaved(false); }} required disabled={busy}
              aria-describedby={id === "new" ? "change-password-hint" : undefined} className="h-11 px-4" />
            {id === "new" && <span id="change-password-hint" className="block text-xs font-normal leading-5 text-muted-foreground">{t("setup.passwordHint")}</span>}
          </div>)}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button type="button" variant="ghost" size="sm" onClick={() => setVisible(value => !value)} disabled={busy}>
              {visible ? <EyeOff className="mr-2 h-4 w-4" aria-hidden /> : <Eye className="mr-2 h-4 w-4" aria-hidden />}{t(visible ? "app.auth.hidePassword" : "app.auth.showPassword")}
            </Button>
            <Button type="submit" disabled={busy}>{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />}{t("settings.account.changePassword")}</Button>
          </div>
          {saved && <p role="status" className="text-sm leading-6 text-muted-foreground">{t("settings.account.saved")}</p>}
        </form></SettingsGroup>
      </section>
    </>}
  </div>;
}
