import { conversationRole } from "@/lib/conversation-role";
import { sortProjectSessions } from "@/lib/chat-groups";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { ConversationCatalog } from "./context";

export function projectConversationCatalog(catalog: Pick<ConversationCatalog, "sessions" | "projects" | "preferences" | "showArchived">, query: string) {
  const preferences = catalog.preferences;
  const archived = new Set(preferences?.archived_keys ?? []);
  const overrides = preferences?.title_overrides ?? {};
  const sessions = sortProjectSessions(catalog.sessions, preferences?.view?.sort ?? "updated_desc", overrides,
    preferences?.session_order ?? [], new Set(preferences?.pinned_keys ?? []), archived);
  const needle = query.trim().toLocaleLowerCase();
  const groups = new Map(catalog.projects.map(project => [project.id, { project, members: [] as ChatSummary[] }]));
  const unfiled: ChatSummary[] = [];
  for (const session of sessions) {
    if (!conversationRole(session.key).inConversations || !catalog.showArchived && archived.has(session.key)) continue;
    const group = groups.get(session.projectId ?? "");
    const projectMatches = group?.project.name.toLocaleLowerCase().includes(needle);
    const text = `${overrides[session.key] ?? session.title ?? ""} ${session.preview} ${session.handle?.name ?? ""}`;
    if (needle && !projectMatches && !text.toLocaleLowerCase().includes(needle)) continue;
    if (group) group.members.push(session); else unfiled.push(session);
  }
  return { groups: [...groups.values()].filter(group => !needle || group.members.length || group.project.name.toLocaleLowerCase().includes(needle)), unfiled };
}
