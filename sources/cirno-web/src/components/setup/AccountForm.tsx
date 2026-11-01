import { useState, type FormEvent } from "react";
import { ArrowRight, Eye, EyeOff, LoaderCircle, LockKeyhole, UserRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AccountRequestError, accountRequest } from "@/lib/account";
import { useTheme } from "@/hooks/useTheme";

export function AccountForm({ mode, onSuccess }: { mode: "register" | "login"; onSuccess: () => void }) {
  const { t } = useTranslation();
  useTheme();
  const register = mode === "register";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (register && (Array.from(password).length < 10 || !/\p{Lu}/u.test(password) || !/[\p{P}\p{S}]/u.test(password))) {
      setError(t("setup.errors.invalid_password"));
      return;
    }
    if (register && password !== confirm) {
      setError(t("setup.errors.password_mismatch"));
      return;
    }
    setBusy(true);
    try {
      await accountRequest(mode, { username: username.trim(), password });
      onSuccess();
    } catch (reason) {
      setError(reason instanceof AccountRequestError
        ? t(`setup.errors.${reason.code}`, { defaultValue: t("setup.errors.request_failed") })
        : t("setup.errors.connection_failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex h-full w-full flex-col overflow-y-auto bg-background">
      <div className="mx-5 mt-5 shrink-0 self-end sm:mx-8">
        <LanguageSwitcher className="h-8 min-w-0 gap-2 px-3 text-xs" />
      </div>
      <div className="flex flex-1 items-center justify-center px-6 pb-12 pt-8 sm:pb-20">
        <section aria-labelledby="account-title" className="w-full max-w-sm">
          <img src="/brand/cirno_snowflake_mark.svg" alt="" width={56} height={56} className="mx-auto mb-6 h-14 w-14" />
          {register && <p className="mb-3 text-center text-xs font-medium text-muted-foreground">{t("setup.step", { current: 1, total: 2 })}</p>}
          <h1 id="account-title" className="text-center text-2xl font-semibold tracking-tight">{t(register ? "setup.registerTitle" : "setup.loginTitle")}</h1>
          <p className="mt-3 text-center text-sm leading-6 text-muted-foreground">{t(register ? "setup.registerDescription" : "setup.loginDescription")}</p>
          <form onSubmit={(event) => { void submit(event); }} className="mt-8 space-y-5">
            <label className="block space-y-2 text-sm font-medium">
              <span className="flex items-center gap-2"><UserRound className="h-4 w-4 text-muted-foreground" aria-hidden />{t("setup.username")}</span>
              <Input name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={(event) => setUsername(event.target.value)} required maxLength={64} disabled={busy} autoFocus className="h-11 px-4" />
            </label>
            <div className="space-y-2">
              <label htmlFor="account-password" className="flex items-center gap-2 text-sm font-medium"><LockKeyhole className="h-4 w-4 text-muted-foreground" aria-hidden />{t("setup.password")}</label>
              <div className="relative">
                <Input id="account-password" name="password" type={visible ? "text" : "password"} autoComplete={register ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} required minLength={register ? 10 : undefined} disabled={busy} aria-describedby={register ? "password-hint" : undefined} className="h-11 px-4 pr-12" />
                <Button type="button" variant="ghost" size="icon" disabled={busy} aria-label={t(visible ? "app.auth.hidePassword" : "app.auth.showPassword")} onClick={() => setVisible(!visible)} className="absolute right-1 top-1/2 h-9 w-9 -translate-y-1/2 rounded-full text-muted-foreground">{visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</Button>
              </div>
              {register && <p id="password-hint" className="text-xs leading-5 text-muted-foreground">{t("setup.passwordHint")}</p>}
            </div>
            {register && <label className="block space-y-2 text-sm font-medium">
              <span>{t("setup.confirmPassword")}</span>
              <Input name="confirmPassword" type={visible ? "text" : "password"} autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} required disabled={busy} className="h-11 px-4" />
            </label>}
            {error && <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm leading-6 text-destructive">{error}</p>}
            <Button type="submit" disabled={busy} className="h-11 w-full gap-2 rounded-full">{busy ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : null}{t(register ? "setup.createAccount" : "setup.signIn")}{!busy && <ArrowRight className="h-4 w-4" aria-hidden />}</Button>
          </form>
          {register && <p className="mt-5 text-center text-xs leading-5 text-muted-foreground">{t("setup.instanceOwner")}</p>}
        </section>
      </div>
    </main>
  );
}
