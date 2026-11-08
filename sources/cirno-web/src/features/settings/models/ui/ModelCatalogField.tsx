import {
  Alert,
  Button,
  ComboBox,
  Description,
  Input,
  Label,
  ListBox,
  Spinner,
} from "@heroui/react";
import { ChevronDown } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useProviderModelCatalog } from "@/hooks/useProviderModelCatalog";
import type { ProviderModelInfo } from "@/lib/contracts/models";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { catalogPolicy } from "../model/catalog";
import { CatalogFeedback } from "./CatalogFeedback";
import "../models.css";

const empty = {};
export function ModelCatalogField({
  token,
  provider,
  value,
  onChange,
  onSelect,
  onSignIn,
  signingIn,
}: {
  token: string;
  provider?: SettingsPayload["providers"][number];
  value: string;
  onChange: (id: string, info?: ProviderModelInfo) => void;
  onSelect?: () => void;
  onSignIn?: (provider: string) => void;
  signingIn?: boolean;
}) {
  const { t } = useTranslation();
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const policy = catalogPolicy(provider, query);
  const catalog = useProviderModelCatalog({
    revision: provider ?? empty,
    token,
    provider: provider?.id ?? "",
    enabled: open && policy.enabled,
  });
  const options = useMemo(
    () =>
      (catalog.payload?.models ?? [])
        .filter((model) =>
          [model.id, model.label, model.description, model.owned_by].some((text) =>
            text?.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
          ),
        )
        .slice(0, 80),
    [catalog.payload, query],
  );
  if (catalog.needsSignIn)
    return (
      <Alert status="warning" role="alert">
        <Alert.Content>
          <Alert.Description>{t("settings.models.catalogAuthRequired")}</Alert.Description>
          <Description>{value}</Description>
          {onSignIn && provider && (
            <Button autoFocus isPending={signingIn} onPress={() => onSignIn(provider.id)}>
              {t("settings.oauth.signInAgain")}
            </Button>
          )}
        </Alert.Content>
      </Alert>
    );
  return (
    <div className="model-catalog-field">
      <ComboBox
        allowsEmptyCollection
        allowsCustomValue
        inputValue={value}
        selectedKey={selected}
        items={options}
        isDisabled={!provider?.configured}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setQuery("");
        }}
        onInputChange={(text) => {
          setQuery(text);
          onChange(text);
        }}
        onSelectionChange={(key) => {
          setSelected(key === null ? null : String(key));
          if (key !== null) {
            onSelect?.();
            onChange(
              String(key),
              catalog.payload?.models.find((row) => row.id === key),
            );
            inputRef.current?.focus();
          }
        }}
      >
        <Label>{t("settings.rows.model")}</Label>
        <ComboBox.InputGroup>
          <Input
            ref={inputRef}
            placeholder={t("settings.models.searchModels")}
            autoComplete="off"
            spellCheck={false}
          />
          <ComboBox.Trigger>
            {catalog.loading ? <Spinner size="sm" /> : <ChevronDown size={16} />}
          </ComboBox.Trigger>
        </ComboBox.InputGroup>
        <ComboBox.Popover className="model-catalog-popover">
          {catalog.failed && (
            <CatalogFeedback
              listRef={listRef}
              payload={catalog.payload}
              error={catalog.error}
              busy={catalog.refreshing}
              onRetry={() => void catalog.retry()}
            />
          )}
          <ListBox<ProviderModelInfo>
            ref={listRef}
            renderEmptyState={() => (
              <p role="status" aria-busy={catalog.loading} className="provider-empty">
                {t(
                  catalog.loading
                    ? "settings.models.loadingModels"
                    : policy.manual
                      ? "settings.models.unsupportedModelList"
                      : policy.waitingForQuery
                        ? "settings.models.searchCatalog"
                        : "settings.models.noModelResults",
                )}
              </p>
            )}
          >
            {(model) => (
              <ListBox.Item id={model.id} textValue={model.id}>
                <div className="model-catalog-option">
                  <Label>{model.label ?? model.id}</Label>
                  {model.label && <Description>{model.id}</Description>}
                  {model.description && <Description>{model.description}</Description>}
                </div>
                <ListBox.ItemIndicator />
              </ListBox.Item>
            )}
          </ListBox>
        </ComboBox.Popover>
      </ComboBox>
      {!provider?.configured && (
        <Description>{t("settings.models.providerNotConfigured")}</Description>
      )}
      {!open && policy.manual && (
        <Description>{t("settings.models.unsupportedModelList")}</Description>
      )}
      {!open && policy.waitingForQuery && (
        <Description>{t("settings.models.searchCatalog")}</Description>
      )}
    </div>
  );
}
