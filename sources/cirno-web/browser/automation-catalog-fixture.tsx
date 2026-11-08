import { useState } from "react";
import { AutomationsPage } from "@/features/automations/AutomationsPage";
import { AutomationEditDialog } from "@/features/automations/edit/AutomationEditDialog";
import { AutomationDeleteDialog } from "@/features/automations/ui/AutomationDeleteDialog";
import { SessionAutomationsDialog } from "@/features/automations/session/SessionAutomationsDialog";
import type { AutomationFilter } from "@/features/automations/model/status";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import { useTheme } from "@/hooks/useTheme";

function examples(): SessionAutomationJob[] {
  const now = new Date(),
    run = new Date(now.getFullYear(), now.getMonth(), 15, 9).getTime();
  const task: SessionAutomationJob = {
    id: "daily",
    name: "Research checkpoint",
    enabled: true,
    schedule: { kind: "every", every_ms: 62500 },
    payload: {
      message:
        "Review experimental results.\nRecord decisions with evidence.\n".repeat(
          8,
        ),
    },
    origin: {
      channel: "websocket",
      session_key: "websocket:research",
      title: "Research",
    },
    state: {
      next_run_at_ms: run,
      run_history: [
        {
          run_at_ms: run - 3_600_000,
          status: "ok",
          duration_ms: 0,
          webui_session_key: "websocket:original-research",
        },
        {
          run_at_ms: run - 1_800_000,
          status: "error",
          error: "Fixture historical command failed",
          webui_session_key: null,
        },
      ],
    },
  };
  return [
    task,
    {
      ...task,
      id: "failed",
      name: "Failed experiment",
      state: {
        last_status: "error",
        last_error: "SSH connection dropped",
        next_run_at_ms: run,
      },
    },
    { ...task, id: "paused", name: "Paused review", enabled: false, state: {} },
    {
      ...task,
      id: "trigger",
      name: "GPU availability",
      kind: "local_trigger",
      schedule: { kind: "local" },
      payload: { message: "nvidia-smi", command: "nvidia-smi" },
      state: {},
    },
    { ...task, id: "heartbeat", name: "System Heartbeat", protected: true },
  ];
}
export function AutomationCatalogFixture() {
  useTheme();
  const [jobs, setJobs] = useState(examples);
  const [filter, setFilter] = useState<AutomationFilter>("all");
  const [editing, setEditing] = useState<SessionAutomationJob | null>(null),
    [deleting, setDeleting] = useState<SessionAutomationJob | null>(null);
  const [returnTo, setReturnTo] = useState<SessionAutomationJob | null>(null);
  const [actions, setActions] = useState<string[]>([]);
  return (
    <main className="min-h-screen bg-background p-4 text-foreground sm:p-8">
      <div className="mx-auto max-w-5xl">
        <div className="mb-6 flex justify-between">
          <h1 className="text-xl font-semibold">Automations</h1>
          <SessionAutomationsDialog
            title="Research"
            jobs={jobs.filter((job) => !job.protected)}
            loading={false}
            loadError={null}
            now={Date.now()}
            onAction={async () => jobs}
            onEdit={async () => jobs}
          />
        </div>
        <AutomationsPage
          payload={{ jobs }}
          loading={false}
          filter={filter}
          actionKey={null}
          error={null}
          onFilterChange={setFilter}
          onRequestEdit={setEditing}
          onRequestDelete={setDeleting}
          returnToDetailJob={returnTo}
          onReturnToDetailHandled={() => setReturnTo(null)}
          onAction={(action, job) => {
            setActions((previous) => [...previous, `${action}:${job.id}`]);
            setJobs((previous) =>
              previous.map((row) =>
                row.id !== job.id
                  ? row
                  : { ...row, enabled: action !== "disable" },
              ),
            );
          }}
        />
        <AutomationEditDialog
          job={editing}
          saving={false}
          onOpenChange={(open) => {
            if (!open) setEditing(null);
          }}
          onCancel={setReturnTo}
          onSave={(job, values) => {
            setJobs((previous) =>
              previous.map((row) =>
                row.id !== job.id
                  ? row
                  : {
                      ...row,
                      name: values.name ?? row.name,
                      payload: {
                        ...row.payload,
                        message: values.message ?? row.payload.message,
                      },
                      schedule: values.schedule ?? row.schedule,
                    },
              ),
            );
            setEditing(null);
          }}
        />
        <AutomationDeleteDialog
          job={deleting}
          deleting={false}
          onOpenChange={(open) => {
            if (!open) setDeleting(null);
          }}
          onConfirm={(job) => {
            setJobs((previous) => previous.filter((row) => row.id !== job.id));
            setDeleting(null);
          }}
        />
        <output hidden data-testid="automation-actions">
          {JSON.stringify(actions)}
        </output>
      </div>
    </main>
  );
}
