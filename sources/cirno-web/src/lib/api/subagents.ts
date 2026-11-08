/** Subagents operations for the versioned Cirno API. */

import type {
  SubagentTaskSnapshot,
  SubagentTasksPayload,
} from "@/lib/contracts/messages";
import { API_READ_TIMEOUT_MS, mutation, request } from "./transport";
import { isRecord } from "../record";
import { parseWebuiThreadPayload } from "./history";
import { isSubagentTask } from "../subagent-tasks";
import type { WebuiThreadPersistedPayload } from "@/lib/contracts/history";
import type { WebUIMutationTransport } from "./transport";

export async function fetchSubagentTasks(
  token: string,
  sessionKey: string,
): Promise<SubagentTasksPayload> {
  const payload = await request<unknown>(
    `/v0/sessions/${encodeURIComponent(sessionKey)}/subagents`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
  if (
    !isRecord(payload) ||
    !Array.isArray(payload.tasks) ||
    !payload.tasks.every(isSubagentTask) ||
    new Set(payload.tasks.map((task) => task.task_id)).size !==
      payload.tasks.length
  ) {
    throw new Error("Invalid subagent tasks response");
  }
  return { tasks: payload.tasks };
}

export async function fetchSubagentThread(
  token: string,
  sessionKey: string,
  taskId: string,
  signal?: AbortSignal,
): Promise<WebuiThreadPersistedPayload> {
  const payload = await request<unknown>(
    `/v0/sessions/${encodeURIComponent(sessionKey)}/subagents/${encodeURIComponent(taskId)}/webui-thread`,
    token,
    { signal, cache: "no-store" },
    API_READ_TIMEOUT_MS,
  );
  return parseWebuiThreadPayload(payload);
}

export async function cancelSubagentTask(
  transport: WebUIMutationTransport,
  sessionKey: string,
  taskId: string,
): Promise<SubagentTaskSnapshot> {
  const result = await mutation<unknown>(transport, "subagent.cancel", {
    session_key: sessionKey,
    task_id: taskId,
  });
  if (!isSubagentTask(result) || result.task_id !== taskId)
    throw new Error("Invalid subagent cancellation response");
  return result;
}
