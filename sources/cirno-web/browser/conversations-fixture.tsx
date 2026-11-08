import { useCallback, useEffect, useMemo, useState } from "react";
import { ConversationCatalogContext, type ConversationCatalog } from "@/features/conversations/catalog/context";
import { ConversationsPage } from "@/features/conversations/ConversationsPage";
import { useProjects } from "@/features/conversations/projects/useProjects";
import type { CirnoClient } from "@/lib/cirno-client";
import type { ChatSummary, ProjectSummary } from "@/lib/contracts/conversations";

const session = (id: string, title: string, projectId?: string): ChatSummary => ({
  key: `websocket:${id}`, chatId: id, channel: "websocket", title, preview: "Saved research",
  createdAt: null, updatedAt: null, projectId,
});
export function ConversationsFixture() {
  const [active, setActive] = useState(true);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => { if (event.key === "F8") setActive(value => !value); };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  const server = useMemo(() => {
    const flags = new URLSearchParams(location.search);
    let projects: ProjectSummary[] = [{ id: "research", name: "Research", working_directory: "/same" }];
    let sessions = [session("cirno", "Cirno"), session("paper", "Review paper", "research"), session("data", "Inspect data"), session("note", "Ungrouped note")];
    if (flags.has("many")) sessions.push(...Array.from({ length: 1500 }, (_, index) => session(`bulk-${index}`, `Research record ${index}`)));
    const attempts = new Map<string, number>();
    const client = {
      onStatus: (handler: (status: string) => void) => { handler("open"); return () => {}; },
      onSessionUpdate: () => () => {},
      requestMutation: async (_method: string, args: { action: string; values?: Record<string, string> }) => {
        const { action, values = {} } = args;
        const attempt = (attempts.get(action) ?? 0) + 1; attempts.set(action, attempt);
        if (action === "projects.list") return { projects };
        const failure = { "projects.save": "saveFailure", "projects.delete": "deleteFailure", "projects.assign": "assignFailure" }[action];
        if (failure && flags.has(failure) && attempt === 1) throw new Error(`Project ${action.split(".")[1]} unavailable`);
        if (action === "projects.save") {
          const project = { ...values, id: values.id || `project-${attempt}`, name: values.name, working_directory: values.working_directory };
          projects = values.id ? projects.map(row => row.id === values.id ? { ...row, ...project } : row) : [...projects, project];
          return { project, projects };
        }
        if (action === "projects.delete") {
          projects = projects.filter(row => row.id !== values.id);
          sessions = sessions.map(row => row.projectId === values.id ? { ...row, projectId: null } : row);
          return { projects };
        }
        if (action === "projects.assign") {
          sessions = sessions.map(row => row.key === values.session_key ? { ...row, projectId: values.project_id || null } : row);
          return { ok: true };
        }
        throw new Error(`No fixture action: ${action}`);
      },
    } as unknown as CirnoClient;
    return { client, readSessions: () => sessions };
  }, []);
  const [sessions, setSessions] = useState(server.readSessions);
  const refreshSessions = useCallback(async () => { setSessions(server.readSessions()); }, [server]);
  const records = useProjects(server.client, refreshSessions);
  const [preferences, setPreferences] = useState<NonNullable<ConversationCatalog["preferences"]>>({ pinned_keys: [], archived_keys: [], title_overrides: {} });
  const catalog: ConversationCatalog = {
    owner: server.client, sessions, projects: records.projects, loading: records.loading,
    projectError: records.error, retryProjects: records.retry, assigning: records.assigning,
    saveProject: records.save, deleteProject: records.remove, assign: (key, id) => { void records.assign(key, id); },
    preferences, showArchived: false, toggleArchived: () => {}, open: () => {}, create: () => {},
    rename: async (key, title) => setPreferences(old => ({ ...old, title_overrides: { ...old.title_overrides, [key]: title } })),
    togglePin: () => {}, toggleArchive: () => {}, deleteConversation: () => {}, deleteMany: () => {}, archiveMany: () => {}, setSort: () => {},

  };
  return <main style={{ height: "100dvh" }}>
    {!active && <p role="status">Another tab</p>}
    <div hidden={!active} style={{ height: "100%" }}><ConversationCatalogContext.Provider value={catalog}><ConversationsPage active={active} /></ConversationCatalogContext.Provider></div>
  </main>;
}
