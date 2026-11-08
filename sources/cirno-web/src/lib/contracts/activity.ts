/** Activity contracts shared by the browser and its transports. */

/** Structured UI blob on ``progress`` WS frames; channels may add more ``kind`` values later. */
export interface AgentUIBlob {
  kind: string;
  data?: unknown;
}

/** WebSocket snapshot for sustained goals (`goal_state` events; keyed by ``chat_id``). */
export interface GoalStateWsPayload {
  active: boolean;
  status?:
    | "active"
    | "blocked"
    | "paused"
    | "waiting"
    | "stopped"
    | "completed"
    | "cancelled";
  continuation_limit?: number;
  continuation_rounds?: number;
  wake_at?: string;
  ui_summary?: string;
  objective?: string;
  recap?: string;
}

export interface ToolProgressEvent {
  version?: number;
  phase?: "start" | "end" | "error" | string;
  call_id?: string;
  name?: string;
  arguments?: unknown;
  result?: unknown;
  error?: unknown;
  files?: unknown[];
  embeds?: unknown[];
}

export interface UIFileDiff {
  format: "unified" | string;
  context?: number;
  truncated?: boolean;
  text?: string;
}

export interface UIFileEdit {
  version?: number;
  call_id: string;
  tool: string;
  path: string;
  absolute_path?: string;
  phase?: "start" | "end" | "error" | string;
  added: number;
  deleted: number;
  approximate?: boolean;
  status: "editing" | "done" | "error";
  operation?: "create" | "edit" | "delete" | string;
  binary?: boolean;
  error?: string;
  pending?: boolean;
  diff?: UIFileDiff;
}
