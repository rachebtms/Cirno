import { Accordion, Button, Form } from "@heroui/react";
import { ArrowRight } from "lucide-react";
import { useRef, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { EntryLayout } from "./ui/EntryLayout";
import { PasswordField } from "./ui/PasswordField";

export function AccessEntry({ failed, onSecret }: { failed: boolean; onSecret: (secret: string) => void }) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<"required" | "invalid" | null>(failed ? "invalid" : null);
  const input = useRef<HTMLInputElement>(null);
  return <EntryLayout title={t("app.auth.title")}>
    <Form className="entry-fields" validationBehavior="aria" onSubmit={event => {
      event.preventDefault();
      if (busy) return;
      const secret = value.trim();
      if (!secret) { setValue(""); setError("required"); input.current?.focus(); return; }
      setBusy(true); onSecret(secret);
    }}>
      <PasswordField autoFocus inputRef={input} label={t("app.auth.label")} name="webui-access-password" value={value} onChange={next => { setValue(next); setError(null); }}
        disabled={busy} visible={visible} onToggle={() => setVisible(previous => !previous)} errorMessage={error ? t(`app.auth.${error}`) : undefined} />
      <Button type="submit" isPending={busy}>{t("app.auth.submit")}<ArrowRight aria-hidden size={16} /></Button>
    </Form>
    <Accordion className="entry-help"><Accordion.Item id="help"><Accordion.Heading><Accordion.Trigger>{t("app.auth.helpTitle")}<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body><p>{t("app.auth.helpConfig")}</p><code>~/.cirno/config.json</code>
        <p>{t("app.auth.helpSecret")}</p><code>channels.websocket.tokenIssueSecret</code>
        <p><Trans i18nKey="app.auth.helpFallback" components={{ code: <code /> }} /></p>
      </Accordion.Body></Accordion.Panel>
    </Accordion.Item></Accordion>
  </EntryLayout>;
}
