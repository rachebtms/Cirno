/** Conversation catalog preferences shared by the browser and its transports. */

export type SidebarDensity = "comfortable" | "compact";

export type SidebarSortMode =
  | "updated_desc"
  | "created_desc"
  | "title_asc"
  | "manual";

export interface SidebarViewState {
  density: SidebarDensity;
  show_archived: boolean;
  sort: SidebarSortMode;
}

export interface SidebarStatePayload {
  schema_version: number;
  pinned_keys: string[];
  archived_keys: string[];
  session_order: string[];
  title_overrides: Record<string, string>;
  project_name_overrides: Record<string, string>;
  tags_by_key: Record<string, string[]>;
  collapsed_groups: Record<string, boolean>;
  view: SidebarViewState;
  updated_at?: string | null;
}
