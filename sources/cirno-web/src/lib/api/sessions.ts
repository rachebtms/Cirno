/** Sessions operations for the versioned Cirno API. */

import type { SessionHandle } from "@/lib/contracts/messages";
import type {
  ChatSummary,
  SessionDeleteResult,
} from "@/lib/contracts/conversations";
import type { RecoveryState } from "@/lib/contracts/events";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { API_READ_TIMEOUT_MS, mutation, request } from "./transport";
import type { WebUIMutationTransport } from "./transport";

export function splitKey(key: string): { channel: string; chatId: string } {
  const idx = key.indexOf(":");
  if (idx === -1) return { channel: "", chatId: key };
  return { channel: key.slice(0, idx), chatId: key.slice(idx + 1) };
}

export function normalizeSessionHandle(value: unknown): SessionHandle | null {
  if (!value || typeof value !== "object") return null;
  const handle = value as Partial<SessionHandle>;
  const id = typeof handle.id === "string" ? handle.id.trim() : "";
  const name = typeof handle.name === "string" ? handle.name.trim() : "";
  if (
    !/^handle_[a-f0-9]{32}$/i.test(id) ||
    !name ||
    !/^[\p{L}\p{N}_-]+$/u.test(name)
  )
    return null;
  return { id, name };
}

export async function listSessions(
  token: string,
  base: string = "",
): Promise<ChatSummary[]> {
  type Row = {
    key: string;
    created_at: string | null;
    updated_at: string | null;
    title?: string;
    preview?: string;
    model_preset?: string | null;
    run_started_at?: number | null;
    recovery_state?: RecoveryState | null;
    workspace_scope?: WorkspaceScopePayload | null;
    ptc_mode?: boolean;
    project_id?: string | null;
    role?: "router" | "worker";
    project_locked?: boolean;
    handle?: SessionHandle | null;
  };
  const body = await request<{ sessions: Row[] }>(
    `${base}/v0/sessions`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
  return body.sessions.map((s) => {
    const handle = normalizeSessionHandle(s.handle);
    return {
      key: s.key,
      ...splitKey(s.key),
      createdAt: s.created_at,
      updatedAt: s.updated_at,
      title: s.title ?? "",
      preview: s.preview ?? "",
      modelPreset: s.model_preset ?? null,
      runStartedAt: s.run_started_at ?? null,
      recoveryState: s.recovery_state ?? null,
      projectId: s.project_id ?? null,
      ptcMode: s.ptc_mode === true,
      role: s.role ?? "worker",
      workspaceScope: s.workspace_scope ?? null,
      projectLocked: s.project_locked ?? true,
      handle,
    };
  });
}

export async function deleteSession(
  transport: WebUIMutationTransport,
  key: string,
  optionsOrBase?: { deleteAutomations?: boolean } | string,
): Promise<SessionDeleteResult> {
  const options = typeof optionsOrBase === "string" ? undefined : optionsOrBase;
  return mutation<SessionDeleteResult>(transport, "session.delete", {
    key,
    ...(options?.deleteAutomations ? { delete_automations: true } : {}),
  });
}
