import { Tabs } from "@heroui/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CalendarPanel, MonthNavigation } from "./calendar/CalendarPanel";
import { AutomationDetailDialog } from "./detail/AutomationDetailDialog";
import type { AutomationsPageProps } from "./model/contracts";
import { automationMatchesFilter } from "./model/status";
import { useAutomationInspection } from "./model/useAutomationInspection";
import { InlineError } from "@/ui/feedback/InlineError";
import { AutomationComposer } from "./ui/AutomationComposer";
import { TaskFilter } from "./ui/TaskFilter";
import { TaskList } from "./ui/TaskList";
import "./automations.css";

export function AutomationsPage(props: AutomationsPageProps) {
  const { t, i18n } = useTranslation();
  const state = useAutomationInspection(props);
  const [view, setView] = useState<"tasks" | "calendar">("calendar");
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const visible = state.jobs.filter((job) => !job.protected);
  const filtered = visible.filter((job) =>
    automationMatchesFilter(job, props.filter),
  );
  const loading = props.loading && !props.payload;
  return (
    <section
      className="automations-page"
      aria-label={t("settings.nav.automations")}
      tabIndex={-1}
    >
      <AutomationComposer {...props} />
      <InlineError message={props.error} />
      <Tabs
        selectedKey={view}
        onSelectionChange={(key) => setView(key as typeof view)}
        className="automation-workspace"
      >
        <div className="automation-toolbar">
          <Tabs.List aria-label={t("settings.automations.views.label")}>
            <Tabs.Tab id="tasks">
              {t("settings.automations.views.tasks")}
              <Tabs.Indicator />
            </Tabs.Tab>
            <Tabs.Tab id="calendar">
              {t("settings.automations.views.calendar")}
              <Tabs.Indicator />
            </Tabs.Tab>
          </Tabs.List>
          {!!visible.length && (
            <TaskFilter
              jobs={visible}
              filter={props.filter}
              onChange={props.onFilterChange}
            />
          )}
        </div>
        {view === "calendar" && (
          <MonthNavigation month={month} setMonth={setMonth} />
        )}
        <Tabs.Panel id="tasks">
          <TaskList
            jobs={filtered}
            loading={loading}
            hasJobs={!!visible.length}
            onInspect={state.inspect}
          />
        </Tabs.Panel>
        <Tabs.Panel id="calendar">
          <CalendarPanel
            token={props.token}
            jobs={filtered}
            month={month}
            loading={loading}
            hasJobs={!!visible.length}
            onInspect={state.inspect}
          />
        </Tabs.Panel>
      </Tabs>
      <AutomationDetailDialog
        job={state.selected}
        open={state.open}
        token={props.token}
        locale={i18n.resolvedLanguage ?? i18n.language}
        chatNames={state.chatNames}
        onChangeChat={props.onChangeChat}
        actionKey={props.actionKey}
        error={props.error}
        onOpenChange={state.setOpen}
        onAction={props.onAction}
        onRequestEdit={(job) => state.handOff(props.onRequestEdit, job)}
        onRequestDelete={(job) => state.handOff(props.onRequestDelete, job)}
      />
    </section>
  );
}
