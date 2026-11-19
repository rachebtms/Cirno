import { ClientListeners } from "./client-listeners";
import type { PreferencesSnapshot } from "@/features/preferences/contracts";
import type { ConnectionStatus } from "./contracts/transport";
import type { InboundEvent } from "./contracts/events";
import type { SidebarStatePayload } from "./contracts/conversation-preferences";
import type { WorkspaceScopePayload } from "./contracts/workspaces";
import type { RunState } from "./client-run-ledger";

export interface TaskNotice {
  event: Extract<InboundEvent, { event: "turn_end" | "recovery_state" }>;
  temporary: boolean;
}
export type StatusHandler = (status: ConnectionStatus) => void;
export type RunCompletionHandler = (chatId: string) => void;
export type RuntimeModelHandler = (modelName: string | null, modelPreset?: string | null) => void;
export type SessionUpdateScope = "metadata" | "thread" | string;
export type SessionUpdateHandler = (
  chatId: string,
  scope?: SessionUpdateScope,
  workspaceScope?: WorkspaceScopePayload,
) => void;
export type SidebarStateUpdateHandler = (state: SidebarStatePayload) => void;
export type RunStatusHandler = (chatId: string, state: RunState) => void;

/** Structured errors surfaced to the UI.
 *
 * Most entries are transport-level or protocol-level faults. Runtime and
 * workspace failures are promoted here when they must remain visible outside
 * the message stream.
 */
export type StreamError =
  /** Server rejected the inbound frame as too large (WS close code 1009).
   * This is the transport fallback after text and attachment policies have
   * already been checked independently. */
  | { kind: "message_too_big"; chatId?: string; turnId?: string }
  | {
      kind: "workspace_scope_rejected";
      reason?: string;
      chatId?: string;
      turnId?: string;
    }
  | {
      kind: "turn_rejected";
      detail?: string;
      reason?: string;
      chatId: string;
      turnId: string;
    }
  | {
      kind: "model_request_failed";
      chatId: string;
      turnId?: string;
      errorKind?: string;
      attempts?: number;
    };

export type ErrorHandler = (error: StreamError) => void;

interface NotificationSnapshots {
  status: () => ConnectionStatus;
  runs: () => Iterable<{ chatId: string; state: RunState }>;
}

/** Shared observer isolation and the two explicit subscription replay policies. */
export class ClientNotifications {
  readonly status = new ClientListeners<Parameters<StatusHandler>>("status");
  readonly runtimeModel = new ClientListeners<Parameters<RuntimeModelHandler>>("runtime model");
  readonly sessionUpdate = new ClientListeners<Parameters<SessionUpdateHandler>>("session update");
  readonly sidebarState = new ClientListeners<Parameters<SidebarStateUpdateHandler>>("sidebar state");
  readonly runStatus = new ClientListeners<Parameters<RunStatusHandler>>("run status");
  readonly completion = new ClientListeners<Parameters<RunCompletionHandler>>("completion");
  readonly error = new ClientListeners<Parameters<ErrorHandler>>("error");
  readonly taskNotice = new ClientListeners<Parameters<(notice: TaskNotice) => void>>("task notice");
  readonly ready = new ClientListeners<Parameters<() => void>>("ready");
  readonly preferences = new ClientListeners<Parameters<(snapshot: PreferencesSnapshot) => void>>("preferences");

  constructor(private readonly snapshots: NotificationSnapshots) {}

  onStatus(handler: StatusHandler): () => void {
    const unsubscribe = this.status.subscribe(handler);
    this.status.invoke(handler, this.snapshots.status());
    return unsubscribe;
  }

  onRunStatus(handler: RunStatusHandler): () => void {
    const unsubscribe = this.runStatus.subscribe(handler);
    for (const { chatId, state } of this.snapshots.runs()) {
      this.runStatus.invoke(handler, chatId, state);
    }
    return unsubscribe;
  }
}
