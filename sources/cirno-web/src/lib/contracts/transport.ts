/** Transport contracts shared by the browser and its transports. */

import type {
  OutboundCliAppMention,
  OutboundMcpPresetMention,
  SessionMention,
  UITurnPhase,
} from "./messages";
import type { WorkspaceScopePayload } from "./workspaces";
import type { SidebarStatePayload } from "./conversation-preferences";

export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "open"
  | "reconnecting"
  | "closed"
  | "error";

export interface InboundTurnMetadata {
  turn_id?: string;
  turn_phase?: UITurnPhase;
  turn_seq?: number;
}

export type Outbound =
  | {
      type: "new_chat";
      request_id?: string;
      workspace_scope?: WorkspaceScopePayload;
      project_id?: string;
      ptc_mode?: boolean;
    }
  | { type: "new_temporary_chat"; request_id?: string; ptc_mode?: boolean }
  | {
      type: "webui_request";
      request_id: string;
      action: string;
      payload: Record<string, unknown>;
    }
  | {
      type: "fork_chat";
      request_id?: string;
      source_chat_id: string;
      before_user_index: number;
      title?: string;
    }
  | { type: "attach"; chat_id: string }
  | { type: "set_sidebar_state"; state: SidebarStatePayload }
  | { type: "discard_temporary_chat"; chat_id: string }
  | {
      type: "set_workspace_scope";
      chat_id: string;
      workspace_scope: WorkspaceScopePayload;
    }
  | {
      type: "message";
      chat_id: string;
      content: string;
      media?: import("../../../packages/client-events/attachments").AttachmentReference[];
      cli_apps?: OutboundCliAppMention[];
      mcp_presets?: OutboundMcpPresetMention[];
      session_mentions?: SessionMention[];
      quoted_context?: string;
      intent?: "create_automation";
      user_shell?: true;
      workspace_scope?: WorkspaceScopePayload;
      turn_id?: string;
      /** Marks messages sent by the embedded WebUI, without changing the
       * generic websocket protocol for other clients. */
      webui?: true;
    };
