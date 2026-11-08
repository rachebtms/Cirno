import { useTranslation } from "react-i18next";
import type { ProviderAdvancedField, ProviderForm } from "./providerForm";
import { RequestParameterField } from "./ui/RequestParameterField";
const fields = [
  { id: "extra_headers", key: "extraHeaders", placeholder: '{\n  "X-Header": "value"\n}', stringsOnly: true },
  { id: "extra_query", key: "extraQuery", placeholder: '{\n  "api-version": "2024-02-01"\n}', stringsOnly: true },
  { id: "extra_body", key: "extraBody", placeholder: '{\n  "service_tier": "priority"\n}', stringsOnly: false },
] as const;
export type RequestParameterDraft = Pick<ProviderForm, "extraHeaders" | "extraQuery" | "extraBody">;
export function ProviderParameterFields({ fields: enabled, form, onChange, onSave, inherit = false, draft = false, disabled = false }: {
  fields: ProviderAdvancedField[]; form: RequestParameterDraft; onChange: (patch: Partial<RequestParameterDraft>) => void;
  onSave?: (patch: Partial<RequestParameterDraft>) => Promise<void>; inherit?: boolean; draft?: boolean; disabled?: boolean;
}) {
  const { t } = useTranslation();
  return <div className="provider-fields">{fields.filter(field => enabled.includes(field.id)).map(field => <RequestParameterField key={field.id}
    field={field.id} title={t(`settings.providers.${field.key}`)} value={form[field.key]} placeholder={field.placeholder} stringsOnly={field.stringsOnly}
    disabled={disabled} inherited={inherit} draft={draft} onChange={value => onChange({ [field.key]: value })}
    onSave={onSave ? value => onSave({ [field.key]: value }) : undefined}
  />)}</div>;
}
