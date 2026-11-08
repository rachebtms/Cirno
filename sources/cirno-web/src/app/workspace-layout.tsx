import { BootstrapAuthRequiredError } from "@/lib/bootstrap";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { projectNameFromPath } from "@/lib/workspace";
import { SESSION_UPDATES_STORAGE_KEY } from "./navigation";
export function readSessionUpdateChatIds(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(SESSION_UPDATES_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return new Set();
    return new Set(
      parsed.filter((item): item is string => typeof item === "string"),
    );
  } catch {
    return new Set();
  }
}

export function writeSessionUpdateChatIds(chatIds: Set<string>): void {
  try {
    window.localStorage.setItem(
      SESSION_UPDATES_STORAGE_KEY,
      JSON.stringify(Array.from(chatIds)),
    );
  } catch {
    // ignore storage errors (private mode, etc.)
  }
}

export function normalizeWorkspaceScope(
  scope: WorkspaceScopePayload,
): WorkspaceScopePayload {
  const accessMode = scope.access_mode;
  return {
    ...scope,
    project_name: scope.project_name ?? projectNameFromPath(scope.project_path),
    access_mode: accessMode,
    restrict_to_workspace: accessMode !== "full",
  };
}

export function isBootstrapAuthRequired(error: unknown): boolean {
  if (error instanceof BootstrapAuthRequiredError) return true;
  const msg = error instanceof Error ? error.message : String(error);
  return msg.includes("HTTP 401") || msg.includes("HTTP 403");
}
