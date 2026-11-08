import { Alert, Button, Description, Form, Input, Label, TextField } from "@heroui/react";
import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAccountEntry } from "./model/useAccountEntry";
import { EntryLayout } from "./ui/EntryLayout";
import { PasswordField } from "./ui/PasswordField";

export function AccountEntry({ mode, onSuccess }: { mode: "register" | "login"; onSuccess: () => void }) {
  const { t, i18n } = useTranslation();
  const state = useAccountEntry(mode, onSuccess);
  return <EntryLayout title={t(state.register ? "setup.registerTitle" : "setup.loginTitle")}
    description={t(state.register ? "setup.registerDescription" : "setup.loginDescription")}
    step={state.register ? t("setup.step", { current: 1, total: 2 }) : undefined}
    footer={state.register ? t("setup.instanceOwner") : undefined}>
    <Form className="entry-fields" validationBehavior="aria" onSubmit={event => { event.preventDefault(); void state.submit(); }}>
      <TextField autoFocus name="username" value={state.username} onChange={state.setUsername} isRequired maxLength={64} isDisabled={state.busy} isInvalid={state.error?.code === "invalid_username"}>
        <Label>{t("setup.username")}</Label><Input autoComplete="username" autoCapitalize="none" spellCheck={false} />
      </TextField>
      {state.register && <TextField name="routerHandle" value={state.routerHandle} onChange={state.setRouterHandle} isRequired maxLength={33}
        isDisabled={state.busy} isInvalid={state.error?.code === "invalid_router_handle"}>
        <Label>{t("setup.routerHandle")}</Label><Input autoCapitalize="none" autoCorrect="off" spellCheck={false} />
        <Description>{t("setup.routerHandleHint")}</Description>
      </TextField>}
      <PasswordField label={t("setup.password")} name="password" value={state.password} onChange={state.setPassword} disabled={state.busy}
        visible={state.visible} onToggle={() => state.setVisible(value => !value)} autoComplete={state.register ? "new-password" : "current-password"}
        help={state.register ? t("setup.passwordHint") : undefined} invalid={state.error?.code === "invalid_password"} />
      {state.register && <PasswordField label={t("setup.confirmPassword")} name="confirmPassword" value={state.confirm} onChange={state.setConfirm} disabled={state.busy}
        visible={state.visible} onToggle={() => state.setVisible(value => !value)} autoComplete="new-password" invalid={state.error?.code === "password_mismatch"} />}
      {state.error && <Alert status="danger" role="alert"><Alert.Content>
        <Alert.Description>{t(`setup.errors.${state.error.code}`, { defaultValue: t("setup.errors.request_failed") })}</Alert.Description>
        {(state.error.detail || !i18n.exists(`setup.errors.${state.error.code}`)) && <pre className="entry-error-detail">{state.error.detail ?? state.error.code}</pre>}
      </Alert.Content></Alert>}
      <Button type="submit" isPending={state.busy}>{t(state.register ? "setup.createAccount" : "setup.signIn")}<ArrowRight aria-hidden size={16} /></Button>
    </Form>
  </EntryLayout>;
}
