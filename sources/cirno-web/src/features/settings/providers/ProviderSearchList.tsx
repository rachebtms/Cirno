import { Button, Header, ListBox, SearchField } from "@heroui/react";
import { Plus, Search } from "lucide-react";
import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { ProviderIcon } from "@/features/settings/shared/ProviderIcon";
import type { ProviderRow } from "./model/contracts";
import { providerGroups } from "./model/providerSearch";

export function ProviderSearchList({
  providers,
  showBrandLogos,
  query,
  onQueryChange,
  onSelect,
  onCustom,
  autoFocus = true,
}: {
  providers: ProviderRow[];
  showBrandLogos: boolean;
  query: string;
  onQueryChange: (value: string) => void;
  onSelect: (id: string) => void;
  onCustom: () => void;
  autoFocus?: boolean;
}) {
  const { t } = useTranslation();
  const groups = useMemo(() => providerGroups(providers, query), [providers, query]);
  const label = t("settings.providers.searchPlaceholder");
  const list = useRef<HTMLDivElement>(null);
  return (
    <>
      <SearchField
        aria-label={label}
        value={query}
        onChange={onQueryChange}
        className="provider-search"
      >
        <SearchField.Group>
          <Search size={17} />
          <SearchField.Input
            autoFocus={autoFocus}
            placeholder={label}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                list.current?.focus();
              }
            }}
          />
          <SearchField.ClearButton />
        </SearchField.Group>
      </SearchField>
      <ListBox
        ref={list}
        aria-label={label}
        className="provider-picker"
        onAction={(key) => onSelect(String(key))}
        renderEmptyState={() => (
          <p role="status" className="provider-empty">
            {t("settings.providers.noMatches")}
          </p>
        )}
      >
        {groups.map((group) => (
          <ListBox.Section key={group.id}>
            <Header>{t(group.labelKey)}</Header>
            {group.providers.map((row) => (
              <ListBox.Item
                key={row.id}
                id={row.id}
                textValue={row.name}
                className="provider-picker-entry"
              >
                <ProviderIcon provider={row.id} showBrandLogos={showBrandLogos} compact />
                <span>{row.name}</span>
              </ListBox.Item>
            ))}
          </ListBox.Section>
        ))}
      </ListBox>
      <div className="provider-custom-action">
        <Button variant="secondary" onPress={onCustom}>
          <Plus size={17} />
          {t("settings.providers.customProvider")}
        </Button>
      </div>
    </>
  );
}
