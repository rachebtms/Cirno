/** Workspaces contracts shared by the browser and its transports. */

export type WorkspaceAccessMode = "restricted" | "review" | "full";

export type WebuiDefaultAccessMode = "default" | "review" | "full";

export interface WorkspaceScopePayload {
  project_path: string;
  project_name?: string;
  access_mode: WorkspaceAccessMode;
  restrict_to_workspace?: boolean;
  sandbox_status?: {
    restrict_to_workspace: boolean;
    workspace_root: string;
    level: string;
    enforced: boolean;
    provider: string;
    provider_label: string;
    summary: string;
  };
}

export interface ProjectDirectory {
  name: string;
  path: string;
}

export interface WorkspaceDirectoriesPayload {
  partial?: boolean;
  path: string;
  parent: string | null;
  entries: ProjectDirectory[];
  truncated: boolean;
  host: string;
  platform: string;
}

export interface WorkspacesPayload {
  schema_version: number;
  default_access_mode: WebuiDefaultAccessMode;
  default_scope: WorkspaceScopePayload;
  recent_projects?: ProjectDirectory[];
  favorite_projects?: ProjectDirectory[];
  host?: { name: string; platform: string };
  controls: {
    can_change_project: boolean;
    can_browse_directories?: boolean;
    can_resolve_project?: boolean;
    can_manage_favorites?: boolean;
  };
}
