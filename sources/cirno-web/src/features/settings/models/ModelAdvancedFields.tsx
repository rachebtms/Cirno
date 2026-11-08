import { Description, FieldError, Input, Label, TextField } from "@heroui/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { formatContextWindowInput, parseContextWindowTokens } from "./modelValues";
import type { AgentSettingsDraft } from "./modelDraft";
type Values = Pick<
  AgentSettingsDraft,
  | "maxTokens"
  | "contextWindowTokens"
  | "idleCompactPercent"
  | "idleCompactKeepPercent"
  | "temperature"
>;
export function ModelAdvancedFields({
  onChange,
  ...values
}: Values & { onChange: (patch: Partial<Values>) => void }) {
  const { t } = useTranslation();
  return (
    <div className="model-advanced-fields">
      <TokenBudget
        label={t("settings.models.maxTokens")}
        value={values.maxTokens}
        onChange={(maxTokens) => onChange({ maxTokens })}
      />
      <TokenBudget
        label={t("settings.rows.contextWindow")}
        value={values.contextWindowTokens}
        onChange={(contextWindowTokens) => onChange({ contextWindowTokens })}
      />
      <TextField>
        <Label>{t("settings.models.temperature")}</Label>
        <Input
          type="number"
          min={0}
          max={2}
          step={0.1}
          value={Number.isFinite(values.temperature) ? values.temperature : ""}
          onChange={(event) =>
            onChange({
              temperature: event.target.value === "" ? NaN : Number(event.target.value),
            })
          }
        />
      </TextField>
      {(["idleCompactPercent", "idleCompactKeepPercent"] as const).map((key) => (
        <TextField key={key}>
          <Label>{t(`settings.models.${key}`)}</Label>
          <Description>{t("settings.models.compactPercentHint")}</Description>
          <Input
            type="number"
            min={0}
            max={100}
            step={0.1}
            placeholder={t("settings.models.inheritGlobal")}
            value={values[key] ?? ""}
            onChange={(event) =>
              onChange({
                [key]: event.target.value === "" ? null : Number(event.target.value),
              })
            }
          />
        </TextField>
      ))}
    </div>
  );
}
function TokenBudget({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<{ text: string; tokens: number } | null>(null);
  const valid = Number.isSafeInteger(value) && value > 0;
  return (
    <TextField
      isRequired
      validationBehavior="aria"
      isInvalid={!valid}
      value={draft && Object.is(draft.tokens, value) ? draft.text : formatContextWindowInput(value)}
      onChange={(text) => {
        const tokens = parseContextWindowTokens(text);
        setDraft({ text, tokens });
        onChange(tokens);
      }}
    >
      <Label>{label}</Label>
      <Input spellCheck={false} />
      {valid && (
        <Description>
          {t("settings.models.contextWindowHint", {
            tokens: value.toLocaleString(),
          })}
        </Description>
      )}
      <FieldError>{t("settings.models.contextWindowError")}</FieldError>
    </TextField>
  );
}
