import type { ChatSummary } from "@/lib/contracts/conversations";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { scopeWithAccessMode } from "@/lib/workspace";
import { normalizeWorkspaceScope } from "./workspace-layout";

/** Shared scope resolution for the focused conversation and retained chat tabs. */
export function conversationScope({ session, temporary, defaultScope, draftScope, overrides }: {
  session: ChatSummary | null; temporary: boolean; defaultScope?: WorkspaceScopePayload | null;
  draftScope?: WorkspaceScopePayload | null; overrides: Record<string, WorkspaceScopePayload>;
}): WorkspaceScopePayload | null {
  if (temporary) return defaultScope ? normalizeWorkspaceScope(scopeWithAccessMode(defaultScope, "restricted")) : null;
  return session ? overrides[session.chatId] ?? session.workspaceScope ?? defaultScope ?? null : draftScope ?? defaultScope ?? null;
}
