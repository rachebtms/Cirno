import { Accordion, Button, Form, Input, Label, ListBox, Select, TextField } from "@heroui/react";
import { Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CalendarInput } from "@/ui/fields/CalendarInput";
import { ToggleField } from "@/ui/fields/ToggleField";
import type { MemoryQuery } from "@/lib/contracts/memory";
import type { MemoryService } from "../model/service";
import type { useMemorySearch } from "../model/useMemorySearch";
import { TagBrowser } from "./TagBrowser";

function Filter({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly (readonly [string, string])[];
  onChange: (value: string) => void;
}) {
  return (
    <Select
      value={value}
      onChange={(key) => {
        if (key !== null) onChange(String(key));
      }}
    >
      <Label>{label}</Label>
      <Select.Trigger>
        <Select.Value />
        <Select.Indicator />
      </Select.Trigger>
      <Select.Popover>
        <ListBox>
          {options.map(([id, label]) => (
            <ListBox.Item key={id} id={id} textValue={label}>
              {label}
              <ListBox.ItemIndicator />
            </ListBox.Item>
          ))}
        </ListBox>
      </Select.Popover>
    </Select>
  );
}
export function MemoryFilters({
  service,
  search,
  compact = false,
}: {
  service: MemoryService;
  compact?: boolean;
  search: ReturnType<typeof useMemorySearch>;
}) {
  const { t } = useTranslation();
  const tr = (key: string) => t(`memoryLibrary.${key}`);
  const { draft, change, apply } = search;
  const filters = [
    {
      key: "mode",
      label: "searchMode",
      options: ["bm25", "semantic", "hybrid"].map((mode) => [mode, tr(`${mode}Mode`)] as const),
    },
    {
      key: "layer",
      label: "layer",
      options: ["all", "event", "knowledge", "task", "source", "profile"].map(
        (layer) => [layer, tr(layer)] as const,
      ),
    },
    {
      key: "scope",
      label: "scope",
      options: ["all", "user", "project", "session"].map((scope) => [scope, tr(scope)] as const),
    },
  ] as const;
  const advanced = <>
      <div className="memory-search-filters">
        {filters.map((filter) => (
          <Filter
            key={filter.key}
            label={tr(filter.label)}
            value={draft[filter.key]}
            options={filter.options}
            onChange={(value) => apply({ [filter.key]: value } as Partial<MemoryQuery>)}
          />
        ))}
      </div>
      <div className="memory-query-row">
        <TextField value={draft.tags} onChange={(tags) => change({ tags })}>
          <Label className="sr-only">{tr("tags")}</Label>
          <Input placeholder={tr("tags")} />
        </TextField>
        <TagBrowser service={service} onSelect={(tags) => apply({ tags })} />
      </div>
      <Accordion>
        <Accordion.Item id="dates">
          <Accordion.Heading>
            <Accordion.Trigger>
              {tr("timeField")}
              <Accordion.Indicator />
            </Accordion.Trigger>
          </Accordion.Heading>
          <Accordion.Panel>
            <div className="memory-date-filter">
              <Filter
                label={tr("timeField")}
                value={draft.timeField}
                options={[
                  ["observed_at", tr("observedAt")],
                  ["created_at", tr("createdAt")],
                  ["updated_at", tr("updatedAt")],
                ]}
                onChange={(timeField) => change({ timeField: timeField as MemoryQuery["timeField"] })}
              />
              <div className="memory-date-range">
                <CalendarInput
                  label={tr("since")}
                  value={draft.since}
                  max={draft.until || undefined}
                  onChange={(since) => change({ since })}
                />
                <CalendarInput
                  label={tr("until")}
                  value={draft.until}
                  min={draft.since || undefined}
                  onChange={(until) => change({ until })}
                />
              </div>
              {search.snapshot?.result.time_zone && (
                <p className="memory-hint">{search.snapshot.result.time_zone}</p>
              )}
              <Button type="submit" variant="secondary" size="sm">
                {tr("filterAction")}
              </Button>
            </div>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
      <ToggleField
        label={tr("includeHistory")}
        selected={draft.includeHistory}
        onChange={(includeHistory) => apply({ includeHistory })}
      />
  </>;
  return (
    <Form
      className="memory-search-form"
      onSubmit={(event) => {
        event.preventDefault();
        void search.submit();
      }}
    >
      <div className="memory-query-row">
        <TextField value={draft.query} onChange={(query) => change({ query })}>
          <Label className="sr-only">{tr("search")}</Label>
          <Input placeholder={tr("search")} />
        </TextField>
        <Button type="submit" isIconOnly isPending={search.loading} aria-label={tr("search")}>
          <Search size={18} />
        </Button>
      </div>
      {compact ? <Accordion><Accordion.Item id="filters"><Accordion.Heading><Accordion.Trigger>
        {t("memoryGraph.filters")}<Accordion.Indicator />
      </Accordion.Trigger></Accordion.Heading><Accordion.Panel><div className="memory-advanced-filters">{advanced}</div></Accordion.Panel></Accordion.Item></Accordion> : advanced}
    </Form>
  );
}
