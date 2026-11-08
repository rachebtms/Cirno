import { Alert, Button, Description, Form, Input, Label, TextField } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { accountRequest, type AccountStatus } from "@/lib/account";
import type { SessionHandle } from "@/lib/contracts/messages";
import { useMutation } from "@/ui/resources/useMutation";

export function RouterNameSettings({ account, onSaved }: {
  account: AccountStatus;
  onSaved: (value: AccountStatus) => void;
}) {
  const { t } = useTranslation();
  const owner = useRef({}).current;
  const mutation = useMutation(owner);
  const [name, setName] = useState(account.router_handle ?? "cirno");
  const [saved, setSaved] = useState(false);
  const [invalid, setInvalid] = useState(false);
  useEffect(() => { setName(account.router_handle ?? "cirno"); }, [account.router_handle]);
  const submit = () => {
    const normalized = name.trim().replace(/^@/, "").toLowerCase();
    setSaved(false);
    if (!/^[a-z][a-z0-9_]{2,31}$/.test(normalized)) { setInvalid(true); return; }
    void mutation.run(() => accountRequest<SessionHandle>("change-router-name", { router_handle: normalized }), identity => {
      onSaved({ ...account, router_handle: identity.name, router_id: identity.id });
      setName(identity.name);
      setSaved(true);
    });
  };
  const error = invalid ? "invalid_router_handle" : mutation.error;
  return <section aria-label={t("setup.routerHandle")}>
    <Form className="account-password-form" validationBehavior="aria" onSubmit={event => { event.preventDefault(); submit(); }}>
      <TextField value={name} onChange={value => { setName(value); setInvalid(false); setSaved(false); mutation.clear(); }}
        isDisabled={mutation.busy} isInvalid={!!error} maxLength={33} isRequired>
        <Label>{t("setup.routerHandle")}</Label><Input autoCapitalize="none" autoCorrect="off" spellCheck={false} />
        <Description>{t("setup.routerHandleHint")}</Description>
      </TextField>
      <p className="account-help">{t("settings.account.routerNameHelp")}</p>
      {error && <Alert status="danger" role="alert"><Alert.Content>{t(`setup.errors.${error}`, { defaultValue: t("setup.errors.connection_failed") })}</Alert.Content></Alert>}
      {saved && <p role="status" className="account-saved">{t("settings.account.routerNameSaved")}</p>}
      <footer><Button type="submit" isPending={mutation.busy}>{t("settings.account.saveRouterName")}</Button></footer>
    </Form>
  </section>;
}
