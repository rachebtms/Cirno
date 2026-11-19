import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { Button, Description, Label, ListBox, Select } from "@heroui/react";
import { useTranslation } from "react-i18next";
import { useClient } from "@/providers/ClientProvider";
import { useMutation } from "@/ui/resources/useMutation";
import type { AgentSettingsDraft } from "../modelDraft";
import { probeModelCapabilities, type CapabilityResults } from "../probeModelCapabilities";

export function ModelCapabilityFields({ form, setForm, disabled, onBusyChange, presetId }: {
  presetId?: string; form: AgentSettingsDraft; setForm: Dispatch<SetStateAction<AgentSettingsDraft>>; disabled: boolean; onBusyChange: (busy: boolean) => void;
}) {
  const { t } = useTranslation(), { client } = useClient();
  const owner = useMemo(() => ({ client, presetId, provider: form.provider, model: form.model,
    api: form.api, reasoningEffort: form.reasoningEffort,
    extraHeaders: form.extraHeaders, extraBody: form.extraBody, extraQuery: form.extraQuery,
  }), [client, presetId, form.provider, form.model,
    form.api, form.reasoningEffort, form.extraHeaders, form.extraBody, form.extraQuery]);
  const probe = useMutation(owner);
  const { busy, error } = probe;
  const [receipt, setReceipt] = useState<{ owner: typeof owner; results: CapabilityResults } | null>(null);
  const results = receipt?.owner === owner ? receipt.results : {};
  useEffect(() => {
    onBusyChange(busy);
    return () => onBusyChange(false);
  }, [busy, onBusyChange]);
  const tr = (key: string) => t(`settings.models.capabilities.${key}`);
  async function test() {
    if (disabled) return;
    await probe.run(
      () => probeModelCapabilities(client, { ...form, imageInput: null, videoInput: null }, presetId),
      result => {
        setReceipt({ owner, results: result });
        setForm(current => current.provider === form.provider && current.model === form.model
          ? { ...current, imageInput: result.image?.supported ?? null, videoInput: result.video?.supported ?? null } : current);
      },
    );
  }
  return <fieldset className="model-preset-fields border-t border-border pt-4" disabled={disabled || busy}>
    <legend className="sr-only">{tr("title")}</legend><h3 className="text-sm font-medium text-foreground">{tr("title")}</h3><Description>{tr("help")}</Description>
    {(["image", "video"] as const).map(kind => {
      const field = kind === "image" ? "imageInput" : "videoInput";
      return <div key={kind}><Select value={form[field] == null ? "auto" : String(form[field])} isDisabled={disabled || busy}
        onChange={key => setForm(current => ({ ...current, [field]: key === "auto" ? null : key === "true" }))}>
        <Label>{tr(kind)}</Label><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
        <Select.Popover><ListBox>{["auto", "true", "false"].map(key => <ListBox.Item key={key} id={key} textValue={tr(key)}>{tr(key)}<ListBox.ItemIndicator /></ListBox.Item>)}</ListBox></Select.Popover>
      </Select>{results[kind] && <Description>{results[kind]!.detail}</Description>}</div>;
    })}
    <Button type="button" variant="secondary" size="sm" isPending={busy} isDisabled={disabled || !form.model || !form.provider} onPress={() => void test()}>{tr("test")}</Button>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
  </fieldset>;
}
