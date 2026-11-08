/** Conversations contracts shared by the browser and its transports. */

import type { RecoveryState } from "../../../packages/client-events/notifications";
import type { SessionAutomationJob } from "./automations";
import type { WorkspaceScopePayload } from "./workspaces";
import type { SessionHandle } from "./messages";

export interface SessionDeleteResult {
  deleted: boolean;
  blocked_by_automations?: boolean;
  automations?: SessionAutomationJob[];
}

export interface ProjectSummary {
  id: string;
  name: string;
  description?: string;
  working_directory?: string;
}

export interface ChatSummary {
  ptcMode?: boolean;
  projectId?: string | null;
  role?: "router" | "worker";
  /** Server-side session key, e.g. ``websocket:abcd-...``. */
  key: string;
  /** Local channel + chat_id parts derived from ``key`` for convenience. */
  channel: string;
  chatId: string;
  createdAt: string | null;
  updatedAt: string | null;
  title?: string;
  preview: string;
  /** Model preset persisted for this session; null means it still follows the global default. */
  modelPreset?: string | null;
  /** Unix epoch seconds when this session currently has a turn in flight. */
  runStartedAt?: number | null;
  /** Durable recovery state that needs attention after an interrupted turn. */
  recoveryState?: RecoveryState | null;
  workspaceScope?: WorkspaceScopePayload | null;
  /** Persisted sessions keep their project; only unpersisted drafts can change it. */
  projectLocked?: boolean;
  /** Immutable ID and mutable, unique display name for this session. */
  handle?: SessionHandle | null;
}
