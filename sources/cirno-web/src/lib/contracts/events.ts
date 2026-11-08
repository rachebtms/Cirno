/** Events contracts shared by the browser and its transports. */

import type {
  NotificationEvent,
  RecoveryState,
} from "../../../packages/client-events/notifications";
import type { PreferencesSnapshot } from "@/features/preferences/contracts";
import type {
  ResponseSource,
  RoundUsage,
  SessionMention,
  SubagentTaskSnapshot,
  TurnUsage,
  UICliAppAttachment,
  UIInputOrigin,
  UIMcpPresetAttachment,
  UIMediaAttachment,
  UIMediaKind,
  UIMessageSource,
  UISessionMessage,
  UITraceDetail,
} from "./messages";
import type { InboundTurnMetadata } from "./transport";
import type {
  AgentUIBlob,
  GoalStateWsPayload,
  ToolProgressEvent,
  UIFileEdit,
} from "./activity";
import type { WorkspaceScopePayload } from "./workspaces";
import type { SidebarStatePayload } from "./conversation-preferences";
export type { RecoveryState } from "../../../packages/client-events/notifications";

export type InboundEvent =
  | { event: "subagent_task"; chat_id: string; task: SubagentTaskSnapshot }
  | { event: "ready"; chat_id: string; client_id: string; upload?: unknown }
  | {
      event: "attached";
      request_id?: string;
      chat_id: string;
      temporary?: boolean;
      recovery_state?: RecoveryState;
      usage?: TurnUsage;
    }
  | {
      event: "message_accepted";
      chat_id: string;
      turn_id: string;
      media_urls?: UIMediaAttachment[];
      starts_turn?: boolean;
      active_turn_id?: string;
      started_at?: number;
    }
  | ({
      event: "user_message";
      chat_id: string;
      text: string;
      turn_id?: string;
      active_turn_id?: string;
      starts_turn: boolean;
      started_at?: number;
      created_at_ms?: number;
      media_urls?: UIMediaAttachment[];
      cli_apps?: UICliAppAttachment[];
      mcp_presets?: UIMcpPresetAttachment[];
      session_mentions?: SessionMention[];
      provenance?: {
        session_message?: UISessionMessage;
        input_origin?: UIInputOrigin;
      };
    } & InboundTurnMetadata)
  | ({
      event: "message";
      chat_id: string;
      text: string;
      render_as?: "text";
      reply_to?: string;
      media?: string[];
      media_urls?: Array<{ url: string; name?: string; kind?: UIMediaKind }>;
      tool_events?: ToolProgressEvent[];
      /** Oversized persisted activity detail, fetched only when the trace is expanded. */
      trace_detail?: UITraceDetail;
      /** Present when the frame is an agent breadcrumb (e.g. tool hint,
       * generic progress line) rather than a conversational reply. */
      kind?: "tool_hint" | "progress" | "reasoning";
      /** Server-measured turn wall time when this frame finishes an assistant reply. */
      latency_ms?: number;
      /** Lightweight provenance for proactive assistant messages. */
      source?: UIMessageSource;
      response_sources?: ResponseSource[];
      /** Optional structured payload on progress frames (channel-specific). */
      agent_ui?: AgentUIBlob;
    } & InboundTurnMetadata)
  | (NotificationEvent & InboundTurnMetadata)
  | ({
      event: "file_edit";
      chat_id: string;
      edits: UIFileEdit[];
    } & InboundTurnMetadata)
  | ({
      event: "delta";
      chat_id: string;
      text: string;
      stream_id?: string;
      /** Lightweight provenance for proactive streamed assistant messages. */
      source?: UIMessageSource;
      response_sources?: ResponseSource[];
    } & InboundTurnMetadata)
  | ({
      event: "stream_end";
      chat_id: string;
      stream_id?: string;
      text?: string;
      /** Lightweight provenance for proactive streamed assistant messages. */
      source?: UIMessageSource;
      response_sources?: ResponseSource[];
      /** This answer segment ended, but the active agent turn will continue. */
      resuming?: boolean;
      /** The next answer segment continues this same assistant message. */
      merge_next?: boolean;
    } & InboundTurnMetadata)
  | ({
      event: "reasoning_delta";
      chat_id: string;
      text: string;
      stream_id?: string;
    } & InboundTurnMetadata)
  | ({
      event: "reasoning_end";
      chat_id: string;
      stream_id?: string;
      /** Legacy persisted transcripts may carry the final reasoning text here. */
      text?: string;
    } & InboundTurnMetadata)
  | {
      event: "runtime_model_updated";
      model_name: string;
      model_preset?: string | null;
    }
  | {
      event: "turn_model_updated";
      chat_id: string;
      model_name: string;
      model_preset?: string | null;
      fallback?: boolean;
      reauth_provider?: string;
    }
  | ({
      event: "turn_end";
      chat_id: string;
      latency_ms?: number;
      usage?: TurnUsage;
      round_usages?: RoundUsage[];
      context_window_tokens?: number;
      /** Authoritative sustained-goal snapshot for this chat (same shape as ``goal_state`` events). */
      goal_state?: GoalStateWsPayload;
      outcome?: "completed" | "failed" | "cancelled" | "interrupted";
      failure_kind?: string;
      failure_error_kind?: string;
      failure_attempts?: number;
      failure_message?: string;
    } & InboundTurnMetadata)
  | ({
      event: "goal_status";
      chat_id: string;
      /** Turn executing (user message through agent loop). */
      status: "running" | "idle";
      /** Server ``time.time()`` when ``status`` is ``running``. */
      started_at?: number;
    } & InboundTurnMetadata)
  | {
      event: "goal_state";
      chat_id: string;
      goal_state: GoalStateWsPayload;
    }
  | {
      event: "session_updated";
      chat_id: string;
      scope?: "metadata" | "thread" | string;
      workspace_scope?: WorkspaceScopePayload;
    }
  | {
      event: "preferences_updated";
      preferences: PreferencesSnapshot;
    }
  | {
      event: "sidebar_state_updated";
      state: SidebarStatePayload;
    }
  | {
      event: "webui_response";
      request_id: string;
      ok: true;
      result: unknown;
    }
  | {
      event: "webui_response";
      request_id: string;
      ok: false;
      error: { status: number; message: string };
    }
  | {
      event: "error";
      request_id?: string;
      chat_id?: string;
      detail?: string;
      reason?: string;
      /** Present when this error rejects a specific outbound WebUI turn. */
      turn_id?: string;
    };

export type ThreadProjectionEventName =
  | "user_message"
  | "message"
  | "file_edit"
  | "delta"
  | "stream_end"
  | "reasoning_delta"
  | "reasoning_end"
  | "context_compaction"
  | "turn_end";

export type ThreadProjectionEvent = Extract<
  InboundEvent,
  { event: ThreadProjectionEventName }
> & {
  projection_id?: string;
  created_at_ms?: number;
  turn_seq?: number;
  /** Actual facts represented by a compacted HTTP projection event. */
  projection_receipts?: Array<{
    turn_id: string;
    ranges: Array<[number, number]>;
  }>;
};
