import type { CirnoClient } from "@/lib/cirno-client";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";

export function fileRequest(
  client: CirnoClient,
  sessionKey: string | null,
  scope?: WorkspaceScopePayload | null,
) {
  const context = {
    session_key: sessionKey,
    ...(scope
      ? {
          workspace_scope: {
            project_path: scope.project_path,
            access_mode: scope.access_mode,
          },
        }
      : {}),
  };
  return <T>(action: string, values: Record<string, unknown>) =>
    client.requestMutation<T>(`workspace.files.${action}`, {
      ...context,
      ...values,
    });
}
