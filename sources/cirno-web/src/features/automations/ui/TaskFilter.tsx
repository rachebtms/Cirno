import { Button, Dropdown } from "@heroui/react";
import { ListFilter } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import {
  automationMatchesFilter,
  type AutomationFilter,
} from "../model/status";

const filters = ["all", "active", "paused", "failed"] as const;
export function TaskFilter({
  jobs,
  filter,
  onChange,
}: {
  jobs: SessionAutomationJob[];
  filter: AutomationFilter;
  onChange: (value: AutomationFilter) => void;
}) {
  const { t } = useTranslation();
  const title =
    filter === "all"
      ? t("settings.automations.filter")
      : t("settings.automations.filteredBy", {
          status: t(`settings.automations.filters.${filter}`),
        });
  return (
    <Dropdown>
      <Button
        variant={filter === "all" ? "ghost" : "secondary"}
        size="sm"
        isIconOnly={filter === "all"}
        aria-label={title}
      >
        <ListFilter size={16} />
        {filter !== "all" && title}
      </Button>
      <Dropdown.Popover placement="bottom end">
        <Dropdown.Menu
          aria-label={t("settings.automations.filter")}
          selectionMode="single"
          disallowEmptySelection
          selectedKeys={new Set([filter])}
          onSelectionChange={(keys) => {
            const value = filters.find(
              (value) => keys !== "all" && keys.has(value),
            );
            if (value) onChange(value);
          }}
        >
          {filters.map((value) => (
            <Dropdown.Item
              key={value}
              id={value}
              textValue={t(`settings.automations.filters.${value}`)}
            >
              <Dropdown.ItemIndicator />
              <span>{t(`settings.automations.filters.${value}`)}</span>
              <span className="automation-filter-count">
                {
                  jobs.filter((job) => automationMatchesFilter(job, value))
                    .length
                }
              </span>
            </Dropdown.Item>
          ))}
        </Dropdown.Menu>
      </Dropdown.Popover>
    </Dropdown>
  );
}
