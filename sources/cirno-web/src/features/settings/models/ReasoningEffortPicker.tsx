import { ComboBox, Input, Label, ListBox, Spinner } from "@heroui/react";
import { ChevronDown } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useProviderModelCatalog } from "@/hooks/useProviderModelCatalog";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { CatalogFeedback } from "./ui/CatalogFeedback";

const empty = {};
export function ReasoningEffortPicker({ token, provider, model, savedValues, value, onChange, onSelect }: {
  token: string;
  provider: SettingsPayload["providers"][number] | undefined;
  model: string;
  savedValues?: string[];
  value: string;
  onChange: (value: string) => void;
  onSelect?: () => void;
}) {
  const { t } = useTranslation();
  const defaultLabel = t("settings.values.default");
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const catalog = useProviderModelCatalog({
    revision: provider ?? empty,
    token,
    provider: provider?.id ?? "",
    enabled: open && Boolean(model && provider?.configured && provider.model_catalog !== "unsupported"),
  });
  const efforts = catalog.payload?.models.find(row => row.id === model)?.reasoning_efforts ?? savedValues ?? [];
  const choices = [
    { id: ":default", name: defaultLabel },
    ...[...new Set(efforts.filter(Boolean))].map(id => ({ id, name: id })),
  ];
  return <ComboBox
    allowsCustomValue
    inputValue={value || defaultLabel}
    defaultItems={choices}
    selectedKey={selected}
    onOpenChange={setOpen}
    onInputChange={text => onChange(text === defaultLabel ? "" : text)}
    onSelectionChange={key => {
      setSelected(key === null ? null : String(key));
      if (key !== null) {
        onSelect?.();
        onChange(key === ":default" ? "" : String(key));
        inputRef.current?.focus();
      }
    }}
  >
    <Label>{t("settings.models.reasoningEffort")}</Label>
    <ComboBox.InputGroup>
      <Input ref={inputRef} placeholder={defaultLabel} autoComplete="off" spellCheck={false} />
      <ComboBox.Trigger>{catalog.loading ? <Spinner size="sm" /> : <ChevronDown size={16} />}</ComboBox.Trigger>
    </ComboBox.InputGroup>
    <ComboBox.Popover>
      {catalog.failed && <CatalogFeedback
        listRef={listRef} payload={catalog.payload} error={catalog.error} busy={catalog.refreshing}
        onRetry={() => void catalog.retry()}
      />}
      <ListBox<{ id: string; name: string }> ref={listRef}>{choice => <ListBox.Item id={choice.id} textValue={choice.name}>
        {choice.name}<ListBox.ItemIndicator />
      </ListBox.Item>}</ListBox>
    </ComboBox.Popover>
  </ComboBox>;
}
