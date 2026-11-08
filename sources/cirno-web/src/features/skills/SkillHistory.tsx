import { Accordion, Alert, Button, Form, Input, Label, TextField } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { CirnoClient } from "@/lib/cirno-client";
import { useSkillHistory } from "./model/useSkillHistory";

export function SkillHistory({ client }: { client: CirnoClient }) {
  const { t } = useTranslation();
  const history = useSkillHistory(client);
  return (
    <section className="skill-history-settings">
      <h2 className="mb-4 text-base font-semibold">{t("features.skillHistory")}</h2>
      <Form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void history.validate();
        }}
      >
        <TextField
          className="min-w-0 flex-1"
          isRequired
          isDisabled={history.busy}
          value={history.name}
          onChange={history.changeName}
        >
          <Label>{t("features.skillName")}</Label>
          <Input />
        </TextField>
        <Button type="submit" isPending={history.busy}>
          {t("features.validate")}
        </Button>
      </Form>
      {history.error && (
        <Alert className="mt-4" status="danger" role="alert">
          <Alert.Description>{history.error}</Alert.Description>
        </Alert>
      )}
      {history.result && (
        <div className="mt-4 space-y-3">
          <p className="whitespace-pre-wrap text-sm" role="status">
            {history.result.validation.valid
              ? t("features.validationPassed")
              : history.result.validation.errors.join("\n")}
          </p>
          <p className="text-sm text-muted">{t("features.validationDescription")}</p>
          <Accordion>
            {history.result.versions.map((version) => (
              <Accordion.Item key={version.revision} id={version.revision}>
                <Accordion.Heading>
                  <Accordion.Trigger>
                    <span className="min-w-0 break-all text-sm">{version.revision}</span>
                    <Accordion.Indicator />
                  </Accordion.Trigger>
                </Accordion.Heading>
                <Accordion.Panel>
                  <Accordion.Body>
                    <p className="break-all text-sm">{version.path}</p>
                    <p className="whitespace-pre-wrap text-sm">
                      {version.validation.valid ? t("features.valid") : version.validation.errors.join("\n")}
                    </p>
                  </Accordion.Body>
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
        </div>
      )}
    </section>
  );
}
