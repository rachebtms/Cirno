import type {
  ChatSummary,
  ProjectSummary,
} from "@/lib/contracts/conversations";
import { createContext, useContext } from "react";
import type {
  SidebarStatePayload,
} from "@/lib/contracts/conversation-preferences";
import type { SidebarSortMode } from "@/lib/contracts/conversation-preferences";
import type { ConversationDeleteActions } from "../shared/contracts";
import type { ProjectDraft } from "../projects/service";

export interface ConversationCatalog {
  owner: object;
  sessions: ChatSummary[];
  projects: ProjectSummary[];
  loading: boolean;
  error?: string | null;
  preferencesError?: string | null;
  projectError?: string | null;
  retryProjects?: () => void;
  assigning?: boolean;
  activity?: Readonly<
    Record<string, "running" | "recovery" | "updated" | null>
  >;
  retryPreferences?: () => void;
  open: (key: string) => void;
  create: (project?: ProjectSummary) => void;
  saveProject: (draft: ProjectDraft) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  assign: (key: string, id: string | null) => void;
  preferences?: Pick<
    SidebarStatePayload,
    "pinned_keys" | "archived_keys" | "title_overrides"
  > &
    Partial<Pick<SidebarStatePayload, "session_order" | "view">>;
  showArchived: boolean;
  toggleArchived: () => void;
  rename: (key: string, title: string) => Promise<void>;
  togglePin: (key: string) => void;
  toggleArchive: (key: string) => void;
  deleteConversation: ConversationDeleteActions["onRequestDelete"];
  deleteMany: NonNullable<ConversationDeleteActions["onRequestDeleteMany"]>;
  archiveMany: (keys: string[], archive: boolean) => void;
  setSort: (sort: SidebarSortMode) => void;

}
export const ConversationCatalogContext =
  createContext<ConversationCatalog | null>(null);
export function useConversationCatalog() {
  const catalog = useContext(ConversationCatalogContext);
  if (!catalog)
    throw new Error("The Conversations tab requires its catalog provider");
  return catalog;
}
