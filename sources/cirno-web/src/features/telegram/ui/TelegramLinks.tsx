import {
  Button,
  Card,
  FieldError,
  Form,
  Input,
  Label,
  TextField,
} from "@heroui/react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { InlineError } from "@/ui/feedback/InlineError";
import type { TelegramBindingState } from "../model/useTelegramBinding";
export function TelegramLinks({
  state,
  value,
}: {
  state: TelegramBindingState;
  value: string;
}) {
  const { t } = useTranslation();
  const helpId = useId();
  const [draft, setDraft] = useState<string | null>(null),
    url = draft ?? value;
  const save = async () => {
    if (await state.update({ webui_url: url.trim() }, "links")) setDraft(null);
  };
  return (
    <section className="telegram-section">
      <h2>{t("settings.telegram.actionLinks")}</h2>
      <Card>
        <Card.Content>
          <Form
            className="telegram-url-form"
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <TextField
              value={url}
              onChange={setDraft}
              isDisabled={state.mutation.busy}
              type="url"
              aria-describedby={helpId}
            >
              <Label>{t("settings.telegram.webuiUrl")}</Label>
              <Input placeholder="https://cirno.example.com" />
              <p id={helpId} className="telegram-hint">
                {t("settings.telegram.urlHelp")}
              </p>
              <div className="telegram-field-error">
                <FieldError />
              </div>
            </TextField>
            <InlineError message={state.errorFor("links")} />
            <Button
              type="submit"
              size="sm"
              isDisabled={state.mutation.busy || url.trim() === value}
              isPending={state.mutation.busy && url.trim() !== value}
            >
              {t("features.save")}
            </Button>
          </Form>
        </Card.Content>
      </Card>
    </section>
  );
}
