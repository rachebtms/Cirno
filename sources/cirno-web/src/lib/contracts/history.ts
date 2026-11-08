/** History contracts shared by the browser and its transports. */

import type { ThreadProjectionEvent } from "./events";
import type { WorkspaceScopePayload } from "./workspaces";

/** Response shape for ``GET .../webui-thread`` (server-built transcript replay). */
export interface WebuiThreadPagePayload {
  before_cursor?: string | null;
  has_more_before?: boolean;
  after_cursor?: string | null;
  has_more_after?: boolean;
  user_message_offset?: number;
  loaded_event_count?: number;
  truncated_oversized_turn?: boolean;
}

export interface PromptSummary {
  id: string;
  preview: string;
  answerPreview: string;
  createdAt: number;
  cursor: string;
  turnId: string;
}

export interface DirectoryPrompt extends PromptSummary { index: number }
export interface PromptPage {
  prompts: DirectoryPrompt[];
  offset: number;
  total: number;
  count: number;
  revision: string | null;
}

export interface WebuiThreadPersistedPayload {
  schemaVersion: number;
  sessionKey?: string;
  savedAt?: string;
  /** Cheap server revision used for application-managed conditional revalidation. */
  revision?: string;
  /** Canonical transcript events projected by the same reducer as live events. */
  events: ThreadProjectionEvent[];
  projection: "events";
  fork_boundary_event_index?: number;
  /** Turn ids backed by an explicit persisted ``turn_end`` event. */
  completed_turn_ids?: string[];
  has_pending_tool_calls?: boolean;
  /** Exact active turn when supplied by a current gateway. */
  active_turn_id?: string | null;
  page?: WebuiThreadPagePayload;
  workspace_scope?: WorkspaceScopePayload;
}

export interface WebuiThreadTraceDetailPayload {
  message_id: string;
  events: ThreadProjectionEvent[];
}
