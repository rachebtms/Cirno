import type { CirnoClient } from "@/lib/cirno-client";
import type { ProjectSummary } from "@/lib/contracts/conversations";

export interface ProjectDraft { id?: string; name: string; working_directory: string }

export function projectService(client: CirnoClient) {
  const action = <T>(name: string, values?: object) =>
    client.requestMutation<T>("instance.action", { action: `projects.${name}`, ...(values ? { values } : {}) });
  return {
    list: async () => (await action<{ projects: ProjectSummary[] }>("list")).projects,
    save: (draft: ProjectDraft) => action<{ project: ProjectSummary; projects: ProjectSummary[] }>("save", draft),
    remove: (id: string) => action<{ projects: ProjectSummary[] }>("delete", { id }),
    assign: (key: string, id: string | null) => action<{ ok: true }>("assign", { session_key: key, project_id: id }),
  };
}
