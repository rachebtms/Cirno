import { Alert, Button, Description, Form, Input, Label, Spinner, TextField } from "@heroui/react";
import { Eye, EyeOff, UserRound } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAccountSettings } from "./useAccountSettings";
import { RouterNameSettings } from "./RouterNameSettings";
import "./account.css";

export function AccountSettings() {
  const { t } = useTranslation();
  const state = useAccountSettings();
  const [visible, setVisible] = useState(false);
  if (!state.account) return <div className="account-settings">
    {state.loadError ? <Alert status="danger" role="alert"><Alert.Content>{state.loadError}</Alert.Content>
      <Button variant="secondary" onPress={state.retry}>{t("settings.account.retry")}</Button>
    </Alert> : <Spinner aria-label={t("settings.account.loading")} />}
  </div>;
  if (!state.account.enabled || !state.account.authenticated) return <p className="text-muted">{t("settings.account.unavailable")}</p>;
  const fields = [
    { key: "current", label: "settings.account.currentPassword", autoComplete: "current-password" },
    { key: "next", label: "settings.account.newPassword", autoComplete: "new-password" },
    { key: "confirm", label: "setup.confirmPassword", autoComplete: "new-password" },
  ] as const;
  return <div className="account-settings">
    <section className="account-owner" aria-label={t("settings.account.owner")}>
      <UserRound aria-hidden size={24} /><div><h2>{t("setup.username")}</h2><p>{state.account.username}</p></div>
    </section>
    <RouterNameSettings account={state.account} onSaved={state.setAccount} />
    <section aria-label={t("settings.account.changePassword")}>
      <h2>{t("settings.account.changePassword")}</h2>
      <p className="account-help">{t("settings.account.help")}</p>
      <Form className="account-password-form" validationBehavior="aria" onSubmit={event => { event.preventDefault(); void state.submit(); }}>
        <input type="text" name="username" value={state.account.username ?? ""} readOnly hidden autoComplete="username" />
        {fields.map(field => <TextField key={field.key} name={`${field.key}Password`} value={state.passwords[field.key]} isDisabled={state.busy}
          onChange={value => state.change(field.key, value)}>
          <Label>{t(field.label)}</Label><Input type={visible ? "text" : "password"} autoComplete={field.autoComplete} required />
          {field.key === "next" && <Description>{t("setup.passwordHint")}</Description>}
        </TextField>)}
        {state.error && <Alert status="danger" role="alert"><Alert.Content>{state.error}</Alert.Content></Alert>}
        {state.saved && <p role="status" className="account-saved">{t("settings.account.saved")}</p>}
        <footer>
          <Button type="button" variant="tertiary" onPress={() => setVisible(value => !value)} isDisabled={state.busy}>
            {visible ? <EyeOff size={16} /> : <Eye size={16} />}{t(visible ? "app.auth.hidePassword" : "app.auth.showPassword")}
          </Button>
          <Button type="submit" isPending={state.busy}>{t("settings.account.changePassword")}</Button>
        </footer>
      </Form>
    </section>
  </div>;
}
