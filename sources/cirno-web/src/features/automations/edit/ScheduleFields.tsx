import { Input, Label, ListBox, Select, Tabs, TextField } from "@heroui/react";
import { useTranslation } from "react-i18next";
import {
  AUTOMATION_EVERY_UNITS,
  type AutomationEditDraft,
  type AutomationEveryUnit,
} from "../model/draft";
import { RunAtPicker } from "../ui/RunAtPicker";

export function ScheduleFields({
  draft,
  change,
  disabled,
}: {
  draft: AutomationEditDraft;
  change: (patch: Partial<AutomationEditDraft>) => void;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const types = ["every", "cron", "at"] as const;
  return (
    <section
      className="automation-schedule-fields"
      aria-label={t("settings.automations.fields.scheduleType")}
    >
      <Label>{t("settings.automations.fields.scheduleType")}</Label>
      <Tabs
        selectedKey={draft.scheduleKind}
        onSelectionChange={(key) =>
          change({ scheduleKind: key as AutomationEditDraft["scheduleKind"] })
        }
      >
        <Tabs.List aria-label={t("settings.automations.fields.scheduleType")}>
          {types.map((kind) => (
            <Tabs.Tab key={kind} id={kind} isDisabled={disabled}>
              {t(`settings.automations.scheduleTypes.${kind}`)}
              <Tabs.Indicator />
            </Tabs.Tab>
          ))}
        </Tabs.List>
        <Tabs.Panel id="every">
          <div className="automation-interval-fields">
            <TextField
              isRequired
              isDisabled={disabled}
              value={draft.everyValue}
              onChange={(everyValue) => change({ everyValue })}
            >
              <Label>{t("settings.automations.fields.every")}</Label>
              <Input
                type="number"
                min={1}
                step={1}
                max={Math.floor(
                  Number.MAX_SAFE_INTEGER /
                    AUTOMATION_EVERY_UNITS.find(
                      (unit) => unit.value === draft.everyUnit,
                    )!.ms,
                )}
              />
            </TextField>
            <Select
              isDisabled={disabled}
              value={draft.everyUnit}
              onChange={(key) => {
                if (key !== null)
                  change({ everyUnit: key as AutomationEveryUnit });
              }}
            >
              <Label>{t("settings.automations.fields.unit")}</Label>
              <Select.Trigger>
                <Select.Value>
                  {t(`settings.automations.everyUnits.${draft.everyUnit}`)}
                </Select.Value>
                <Select.Indicator />
              </Select.Trigger>
              <Select.Popover>
                <ListBox>
                  {AUTOMATION_EVERY_UNITS.map((unit) => (
                    <ListBox.Item
                      key={unit.value}
                      id={unit.value}
                      textValue={t(
                        `settings.automations.everyUnits.${unit.value}`,
                      )}
                    >
                      {t(`settings.automations.everyUnits.${unit.value}`)}
                      <ListBox.ItemIndicator />
                    </ListBox.Item>
                  ))}
                </ListBox>
              </Select.Popover>
            </Select>
          </div>
        </Tabs.Panel>
        <Tabs.Panel id="cron">
          <div className="automation-cron-fields">
            <TextField
              isRequired
              isDisabled={disabled}
              value={draft.cronExpr}
              onChange={(cronExpr) => change({ cronExpr })}
            >
              <Label>{t("settings.automations.fields.cronExpression")}</Label>
              <Input
                placeholder="0 9 * * *"
                autoComplete="off"
                className="font-mono"
              />
            </TextField>
            <TextField
              isDisabled={disabled}
              value={draft.tz}
              onChange={(tz) => change({ tz })}
            >
              <Label>{t("settings.automations.fields.timezone")}</Label>
              <Input placeholder="Asia/Shanghai" autoComplete="off" />
            </TextField>
          </div>
        </Tabs.Panel>
        <Tabs.Panel id="at">
          <RunAtPicker
            value={draft.atLocal}
            onChange={(atLocal) => change({ atLocal })}
            disabled={disabled}
          />
        </Tabs.Panel>
      </Tabs>
    </section>
  );
}
