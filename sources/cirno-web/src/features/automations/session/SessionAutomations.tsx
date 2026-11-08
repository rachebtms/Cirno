import { useCallback, useState } from "react";

import type { AutomationAction } from "../model/status";
import { SessionAutomationsDialog } from "@/features/automations/session/SessionAutomationsDialog";
import { useSessionAutomationJobs } from "@/features/automations/model/useSessionAutomationJobs";
import { runAutomationAction, updateAutomation } from "@/lib/api";
import type { WebUIMutationTransport } from "@/lib/api";
import type {
  AutomationUpdatePayload,
  SessionAutomationJob,
} from "@/lib/contracts/automations";

interface SessionAutomationsProps {
  client: WebUIMutationTransport;
  sessionKey: string;
  token: string;
  title: string;
}

export function SessionAutomations({
  client,
  sessionKey,
  token,
  title,
}: SessionAutomationsProps) {
  const [surfacesOpen, setSurfacesOpen] = useState(false);
  const { jobs, loading, loadError, now } = useSessionAutomationJobs(
    surfacesOpen,
    token,
    sessionKey,
  );
  const act = useCallback(
    async (action: AutomationAction, job: SessionAutomationJob) =>
      (await runAutomationAction(client, action, job.id)).jobs,
    [client],
  );
  const edit = useCallback(
    async (job: SessionAutomationJob, values: AutomationUpdatePayload) =>
      (await updateAutomation(client, job.id, values)).jobs,
    [client],
  );
  return (
    <SessionAutomationsDialog
      title={title}
      jobs={jobs}
      loading={loading}
      loadError={loadError}
      now={now}
      onAction={act}
      onEdit={edit}
      onSurfacesOpenChange={setSurfacesOpen}
      calendarHref="#/automations"
    />
  );
}
