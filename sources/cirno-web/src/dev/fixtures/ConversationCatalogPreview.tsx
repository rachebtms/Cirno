/** Local, disposable catalog data for gallery and browser rendering checks. */
import { useRef, useState } from "react";
import { ConversationCatalogContext, type ConversationCatalog } from "@/features/conversations/catalog/context";
import { ConversationsPage } from "@/features/conversations/ConversationsPage";
import type { ChatSummary, ProjectSummary } from "@/lib/contracts/conversations";

export function ConversationCatalogPreview({ sessions: initialSessions, projects: initialProjects = [], loading = false,
  activity, onOpen = () => {}, onRename = () => {},
}: {
  sessions: ChatSummary[]; projects?: ProjectSummary[]; loading?: boolean;
  activity?: ConversationCatalog["activity"]; onOpen?: (key: string) => void; onRename?: (title: string) => void;
}) {
  const [sessions, setSessions] = useState(initialSessions);
  const [projects, setProjects] = useState(initialProjects);
  const [preferences, setPreferences] = useState<NonNullable<ConversationCatalog["preferences"]>>({
    pinned_keys: [], archived_keys: [], title_overrides: {}, session_order: [],
    view: { sort: "updated_desc", density: "comfortable", show_archived: false },
  });
  const counter = useRef(0);
  const owner = useRef({}).current;
  const archiveMany = (keys: string[], archive: boolean) => setPreferences(old => ({ ...old,
    archived_keys: archive ? [...new Set([...old.archived_keys, ...keys])] : old.archived_keys.filter(key => !keys.includes(key)),
  }));
  const catalog: ConversationCatalog = {
    owner, sessions, projects, loading, activity, preferences,
    open: onOpen,
    create: project => {
      const id = `preview-${++counter.current}`;
      setSessions(old => [...old, { key: `websocket:${id}`, chatId: id, channel: "websocket", title: "New conversation",
        projectId: project?.id, preview: "", createdAt: null, updatedAt: null }]);
    },
    saveProject: async draft => { setProjects(old => draft.id ? old.map(project => project.id === draft.id ? { ...project, ...draft } : project) : [...old, { ...draft, id: `project-${++counter.current}` }]); },
    deleteProject: async id => {
      setProjects(old => old.filter(project => project.id !== id));
      setSessions(old => old.map(session => session.projectId === id ? { ...session, projectId: undefined } : session));
    },
    assign: (key, id) => setSessions(old => old.map(session => session.key === key ? { ...session, projectId: id ?? undefined } : session)),
    showArchived: preferences.view!.show_archived,
    toggleArchived: () => setPreferences(old => ({ ...old, view: { ...old.view!, show_archived: !old.view!.show_archived } })),
    rename: async (key, title) => {
      setPreferences(old => ({ ...old, title_overrides: { ...old.title_overrides, [key]: title } })); onRename(title);
    },
    togglePin: key => setPreferences(old => ({ ...old, pinned_keys: old.pinned_keys.includes(key) ? old.pinned_keys.filter(value => value !== key) : [...old.pinned_keys, key] })),
    toggleArchive: key => archiveMany([key], !preferences.archived_keys.includes(key)),
    deleteConversation: (key, _title, decision) => { decision?.(true); setSessions(old => old.filter(session => session.key !== key)); },
    deleteMany: (items, decision) => { decision?.(true); const keys = new Set(items.map(item => item.key)); setSessions(old => old.filter(session => !keys.has(session.key))); },
    archiveMany,
    setSort: sort => setPreferences(old => ({ ...old, view: { ...old.view!, sort } })),
  };
  return <ConversationCatalogContext.Provider value={catalog}><ConversationsPage /></ConversationCatalogContext.Provider>;
}
