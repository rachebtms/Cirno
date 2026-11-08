/** Automations operations for the versioned Cirno API. */

import type {
  AutomationChatUpdate,
  AutomationChatsPayload,
  AutomationUpdatePayload,
  AutomationsPayload,
  SessionAutomationsPayload,
} from "@/lib/contracts/automations";
import { API_READ_TIMEOUT_MS, mutation, request } from "./transport";
import type { WebUIMutationTransport } from "./transport";

export async function fetchSessionAutomations(
  token: string,
  key: string,
  base: string = "",
  signal?: AbortSignal,
): Promise<SessionAutomationsPayload> {
  return request<SessionAutomationsPayload>(
    `${base}/v0/sessions/${encodeURIComponent(key)}/automations`,
    token,
    signal ? { signal } : undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function fetchAutomations(
  token: string,
  base: string = "",
): Promise<AutomationsPayload> {
  return request<AutomationsPayload>(
    `${base}/v0/webui/automations`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function fetchAutomationChats(
  token: string,
  id: string,
  signal?: AbortSignal,
): Promise<AutomationChatsPayload> {
  return request(
    `/v0/webui/automations/chats?id=${encodeURIComponent(id)}`,
    token,
    { signal },
    API_READ_TIMEOUT_MS,
  );
}

export async function changeAutomationChat(
  transport: WebUIMutationTransport,
  id: string,
  values: AutomationChatUpdate,
): Promise<AutomationsPayload> {
  return mutation(transport, "automation.change_chat", { id, values });
}

export async function fetchAutomationRunResult(
  token: string,
  id: string,
  runAtMs: number,
  kind: "cron" | "local_trigger",
  signal?: AbortSignal,
): Promise<{ response: string | null }> {
  const query = new URLSearchParams({ id, run_at_ms: String(runAtMs), kind });
  return request<{ response: string | null }>(
    `/v0/webui/automations/result?${query}`,
    token,
    { signal },
    API_READ_TIMEOUT_MS,
  );
}

export async function runAutomationAction(
  transport: WebUIMutationTransport,
  action: "enable" | "disable" | "delete" | "run",
  id: string,
): Promise<AutomationsPayload> {
  return mutation<AutomationsPayload>(transport, `automation.${action}`, {
    id,
  });
}

export async function updateAutomation(
  transport: WebUIMutationTransport,
  id: string,
  values: AutomationUpdatePayload,
): Promise<AutomationsPayload> {
  return mutation<AutomationsPayload>(transport, "automation.update", {
    id,
    values,
  });
}
