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

export function SessionAutomations(props: SessionAutomationsProps) {
  return <OwnedSessionAutomations key={JSON.stringify([props.token, props.sessionKey])} {...props} />;
}

function OwnedSessionAutomations({
  client,
  sessionKey,
  token,
  title,
}: SessionAutomationsProps) {
  const [surfacesOpen, setSurfacesOpen] = useState(false);
  const { jobs, loading, loadError, now, mutate } = useSessionAutomationJobs(
    surfacesOpen,
    token,
    sessionKey,
  );
  const act = useCallback(
    (action: AutomationAction, job: SessionAutomationJob) =>
      mutate(async () => (await runAutomationAction(client, action, job.id)).jobs),
    [client, mutate],
  );
  const edit = useCallback(
    (job: SessionAutomationJob, values: AutomationUpdatePayload) =>
      mutate(async () => (await updateAutomation(client, job.id, values)).jobs),
    [client, mutate],
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
