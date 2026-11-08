/** Automations contracts shared by the browser and its transports. */

export interface SessionAutomationJob {
  chat_binding_revision?: string;
  id: string;
  name: string;
  enabled: boolean;
  protected?: boolean;
  delete_after_run?: boolean;
  created_at_ms?: number | null;
  updated_at_ms?: number | null;
  kind?: "local_trigger" | "cron" | string;
  schedule: {
    kind: "at" | "every" | "cron" | "local" | string;
    at_ms?: number | null;
    every_ms?: number | null;
    expr?: string | null;
    tz?: string | null;
  };
  payload: {
    message: string;
    kind?: "agent_turn" | "system_event" | "local_trigger" | string;
    command?: string;
  };
  state: {
    next_run_at_ms?: number | null;
    last_run_at_ms?: number | null;
    last_status?: "ok" | "error" | "skipped" | string | null;
    last_error?: string | null;
    pending?: boolean;
    run_history?: Array<{
      run_at_ms: number;
      status: "ok" | "error" | "skipped" | string;
      duration_ms?: number;
      error?: string | null;
      webui_session_key?: string | null; // null: external chat; absent: older host.
    }>;
  };
  origin?: {
    session_key?: string;
    channel: string;
    chat_id?: string;
    title?: string;
    preview?: string;
  } | null;
  trigger?: {
    id: string;
    command: string;
  };
}

export interface SessionAutomationsPayload {
  jobs: SessionAutomationJob[];
}

export interface AutomationsPayload {
  jobs: SessionAutomationJob[];
}

export interface AutomationChat {
  id: string;
  title: string;
  channel: string;
  unavailable?: boolean;
}

export interface AutomationChatsPayload {
  revision: string;
  current: AutomationChat | null;
  chats: AutomationChat[];
}

export interface AutomationChatUpdate {
  target_id: string;
  revision: string;
  message: string;
}

export interface AutomationUpdatePayload {
  name?: string;
  message?: string;
  schedule?: {
    kind: "at" | "every" | "cron";
    at_ms?: number;
    every_ms?: number;
    expr?: string;
    tz?: string;
  };
}
