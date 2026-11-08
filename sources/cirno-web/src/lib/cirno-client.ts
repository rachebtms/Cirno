import { ClientTranscripts } from "./client-transcripts";
import { ClientListeners } from "./client-listeners";
import { ClientChatRequests } from "./client-chat-requests";
import { ClientMutations } from "./client-mutations";
import { ClientConnection, type ClientConnectionOptions } from "./client-connection";
import type { PreferencesSnapshot } from "@/features/preferences/contracts";
import { uploadAttachments, uploadCapability, type AttachmentReference, type UploadCapability } from "../../packages/client-events/attachments";
import { DeliveryReceipts } from "../../packages/client-events/delivery";
import { decodeNotification } from "../../packages/client-events/notifications";
import type { ConnectionStatus, Outbound } from "@/lib/contracts/transport";
import type { InboundEvent } from "@/lib/contracts/events";
import type { OutboundCliAppMention, OutboundMcpPresetMention, OutboundMedia, SessionMention } from "@/lib/contracts/messages";
import type { SidebarStatePayload } from "@/lib/contracts/conversation-preferences";
import type { GoalStateWsPayload } from "@/lib/contracts/activity";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { ClientRunLedger } from "./client-run-ledger";
import type { CanonicalRunSnapshot, RunEffect, RunObservation, RunState } from "./client-run-ledger";

export type { CanonicalRunSnapshot, RunState } from "./client-run-ledger";

/** WebSocket readyState constants, referenced by value to stay portable
 * across runtimes that don't expose a global ``WebSocket`` (tests, SSR). */
const WS_OPEN = 1;

/** Inbound WebSocket ``console.log`` / parse-failure ``console.warn``.
 *
 * - **Dev** (non-production bundle): **on by default** — messages appear at default log level.
 * - **Production**: off unless ``localStorage.setItem('cirno_debug_ws','1')`` (or ``true``).
 * - **Silence anywhere**: ``localStorage.setItem('cirno_debug_ws','0')`` (or ``false`` / ``off``).
 * Values are read on every frame; no reload needed.
 */
function wsInboundDebugEnabled(): boolean {
  if (typeof globalThis === "undefined") return false;
  try {
    if (import.meta.env.MODE === "test") return false;
    const ls = (globalThis as unknown as { localStorage?: Storage }).localStorage;
    const raw = ls?.getItem("cirno_debug_ws")?.trim().toLowerCase() ?? "";
    if (raw === "0" || raw === "false" || raw === "off" || raw === "no") {
      return false;
    }
    if (raw === "1" || raw === "true" || raw === "on" || raw === "yes") {
      return true;
    }
    return !import.meta.env.PROD;
  } catch {
    return !import.meta.env.PROD;
  }
}

/** Shorten streaming text fields so logging stays usable for huge deltas. */
function summarizeInboundWsPayload(ev: InboundEvent): unknown {
  const kind = (ev as { event?: string }).event;
  if (kind === "ready") return { ...ev, upload: "[redacted]" };
  if (kind !== "delta" && kind !== "reasoning_delta") return ev;
  const row = { ...(ev as object) } as Record<string, unknown>;
  const text = typeof row.text === "string" ? row.text : "";
  const max = 240;
  if (text.length > max) {
    row.text = `${text.slice(0, max)}… (${text.length} chars)`;
  }
  return row;
}

type Unsubscribe = () => void;
type EventHandler = (ev: InboundEvent) => void;
export interface TaskNotice {
  event: Extract<InboundEvent, { event: "turn_end" | "recovery_state" }>;
  temporary: boolean;
}
type StatusHandler = (status: ConnectionStatus) => void;
type RunCompletionHandler = (chatId: string) => void;
type RuntimeModelHandler = (modelName: string | null, modelPreset?: string | null) => void;
type SessionUpdateScope = "metadata" | "thread" | string;
type SessionUpdateHandler = (
  chatId: string,
  scope?: SessionUpdateScope,
  workspaceScope?: WorkspaceScopePayload,
) => void;
type SidebarStateUpdateHandler = (state: SidebarStatePayload) => void;
type RunStatusHandler = (chatId: string, state: RunState) => void;

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

type ErrorHandler = (error: StreamError) => void;

interface PendingRequest<T> {
  resolve: (value: T) => void;
  reject: (err: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

const SYSTEM_COMMAND_TURN_PREFIX = "webui-system:";


export function isSystemCommandTurnId(value: string | null | undefined): value is string {
  return typeof value === "string" && value.startsWith(SYSTEM_COMMAND_TURN_PREFIX);
}

export interface CirnoClientOptions extends ClientConnectionOptions {
  /** Maximum UTF-8 bytes accepted for one websocket message. */
  maxFrameBytes?: number;
}

function runObservation(event: InboundEvent): RunObservation | null {
  if (!("chat_id" in event) || !event.chat_id) return null;
  const turnId = "turn_id" in event && typeof event.turn_id === "string" ? event.turn_id : null;
  const base = { chatId: event.chat_id, turnId, systemCommand: isSystemCommandTurnId(turnId) };
  switch (event.event) {
    case "message_accepted":
    case "user_message": {
      const activeTurnId = event.active_turn_id ?? (event.starts_turn ? event.turn_id : undefined);
      if (event.event === "user_message" && event.provenance?.session_message && !activeTurnId) {
        return { ...base, kind: "activity" };
      }
      return {
        ...base,
        kind: event.event === "message_accepted" ? "admission" : "input",
        ...(activeTurnId ? { owner: { turnId: activeTurnId, startedAt: event.started_at } } : {}),
      };
    }
    case "goal_status":
      return { ...base, kind: "status", activity: event.status, startedAt: event.started_at };
    case "turn_end":
      return { ...base, kind: "completed" };
    case "error":
      return { ...base, kind: "rejection" };
    case "delta":
    case "reasoning_delta":
      return { ...base, kind: event.text ? "activity" : "progress" };
    case "stream_end":
      return { ...base, kind: "activity" };
    case "retry_status":
      return { ...base, kind: event.state === "recovered" || event.state === "cleared" ? "progress" : "activity" };
    case "recovery_state":
      // Supersession resolves the old recovery, not the new user turn that caused it.
      return event.status === "recovered" && event.reason === "superseded"
        ? { ...base, kind: "progress" }
        : { ...base, kind: "recovery", active: event.status === "resuming" };
    case "attached":
      return event.recovery_state && event.recovery_state.status !== "recovered"
        ? { ...base, kind: "recovery", active: event.recovery_state.status === "resuming" }
        : { ...base, kind: "progress" };
    case "message":
      return { ...base, kind: "message" };
    default:
      return { ...base, kind: "progress" };
  }
}

/**
 * Singleton WebSocket client that multiplexes chat streams.
 *
 * One socket carries many chat_ids: the server tags every outbound event with
 * ``chat_id``, and this class fans those events out to handlers registered
 * per chat. Reconnects are transparent and re-attach every known chat_id.
 */
export class CirnoClient {
  private readonly connection: ClientConnection;

  private get socket(): WebSocket | null { return this.connection.socket; }
  private get currentUrl(): string { return this.connection.url; }
  private upload: UploadCapability | null = null;
  private receipts = new DeliveryReceipts();
  private statusHandlers = new ClientListeners<Parameters<StatusHandler>>("status");
  private runtimeModelHandlers = new ClientListeners<Parameters<RuntimeModelHandler>>("runtime model");
  private sessionUpdateHandlers = new ClientListeners<Parameters<SessionUpdateHandler>>("session update");
  private sidebarStateUpdateHandlers = new ClientListeners<Parameters<SidebarStateUpdateHandler>>("sidebar state");
  private runStatusHandlers = new ClientListeners<Parameters<RunStatusHandler>>("run status");
  private runCompletionHandlers = new ClientListeners<Parameters<RunCompletionHandler>>("completion");
  private errorHandlers = new ClientListeners<Parameters<ErrorHandler>>("error");
  private taskNoticeHandlers = new ClientListeners<Parameters<(notice: TaskNotice) => void>>("task notice");
  private readyHandlers = new ClientListeners<Parameters<() => void>>("ready");
  private readonly transcripts = new ClientTranscripts(
    chatId => this.attach(chatId), chatId => this.temporaryChatIds.has(chatId),
  );
  // chat_ids we've attached to since connect; re-attached after reconnects
  private knownChats = new Set<string>();
  /** Temporary chats are connection-owned and intentionally not reattached. */
  private temporaryChatIds = new Set<string>();
  private readonly runs = new ClientRunLedger();
  /** Last tracked application frame written, for conservative transport-error attribution. */
  private lastSocketMessageSend: { chatId: string; turnId: string } | null = null;
  /** Latest ``goal_state`` snapshot per ``chat_id`` (multi-session isolation). */
  private goalStateByChatId = new Map<string, GoalStateWsPayload>();
  private readonly chatRequests = new ClientChatRequests(
    frame => this.queueSend(frame),
    id => { this.sendQueue = this.sendQueue.filter(frame => !("request_id" in frame && frame.request_id === id)); },
  );
  private pendingSystemCommands = new Map<string, PendingRequest<void>>();
  private readonly mutations = new ClientMutations(() => this.socket, () => this.maxFrameBytes);
  // Frames queued while the socket is not yet OPEN
  private sendQueue: Outbound[] = [];
  private maxFrameBytes: number | undefined;
  private status_: ConnectionStatus = "idle";
  private readyChatId: string | null = null;
  private foregroundCheck: Promise<void> | null = null;

  constructor(options: CirnoClientOptions) {
    this.maxFrameBytes = this.normalizeMaxFrameBytes(options.maxFrameBytes);
    this.connection = new ClientConnection(options, {
      status: (status) => this.setStatus(status),
      opened: () => this.handleOpen(),
      message: (event) => this.handleMessage(event),
      closed: (event, willReconnect) => this.handleClose(event, willReconnect),
    });
  }

  get status(): ConnectionStatus {
    return this.status_;
  }

  get defaultChatId(): string | null {
    return this.readyChatId;
  }

  /** Update the address and factory used by the next connection. */
  updateUrl(url: string, socketFactory?: (url: string) => WebSocket): void {
    this.connection.updateUrl(url, socketFactory);
  }

  onStatus(handler: StatusHandler): Unsubscribe {
    const unsubscribe = this.statusHandlers.subscribe(handler);
    this.statusHandlers.invoke(handler, this.status_);
    return unsubscribe;
  }

  onRuntimeModelUpdate(handler: RuntimeModelHandler): Unsubscribe {
    return this.runtimeModelHandlers.subscribe(handler);
  }

  onSessionUpdate(handler: SessionUpdateHandler): Unsubscribe {
    return this.sessionUpdateHandlers.subscribe(handler);
  }

  onReady(handler: () => void): Unsubscribe {
    return this.readyHandlers.subscribe(handler);
  }

  private readonly preferenceHandlers = new ClientListeners<Parameters<(snapshot: PreferencesSnapshot) => void>>("preferences");
  onPreferencesUpdate(handler: (snapshot: PreferencesSnapshot) => void): Unsubscribe {
    return this.preferenceHandlers.subscribe(handler);
  }

  onSidebarStateUpdate(handler: SidebarStateUpdateHandler): Unsubscribe {
    return this.sidebarStateUpdateHandlers.subscribe(handler);
  }

  onRunStatus(handler: RunStatusHandler): Unsubscribe {
    const unsubscribe = this.runStatusHandlers.subscribe(handler);
    for (const { chatId, state } of this.runs.states()) {
      this.runStatusHandlers.invoke(handler, chatId, state);
    }
    return unsubscribe;
  }

  /** Live lifecycle events, independent of mounted chats. Never replays history. */
  onTaskNotice(handler: (notice: TaskNotice) => void): Unsubscribe {
    return this.taskNoticeHandlers.subscribe(handler);
  }

  /** Subscribe to transport-level faults (see :type:`StreamError`). */
  onError(handler: ErrorHandler): Unsubscribe {
    return this.errorHandlers.subscribe(handler);
  }

  getRunState(chatId: string): RunState {
    return this.runs.view(chatId);
  }

  /** Restore pending history only within its original lifecycle generation. */
  restorePendingRun(chatId: string, generation: number, turnId: string | null): void {
    this.applyRunEffects(this.runs.transition({ kind: "restore-pending", chatId, generation, turnId }));
  }

  /** Last ``goal_status`` ``started_at`` (unix sec) for *chatId*, if the turn is running. */
  getRunStartedAt(chatId: string): number | null {
    return this.runs.view(chatId).startedAt;
  }

  /** Canonical lifecycle turn currently owning the run, retained after completion. */
  getRunTurnId(chatId: string): string | null {
    return this.runs.view(chatId).latestTurnId;
  }

  isRunCompleted(chatId: string, turnId: string): boolean {
    return this.runs.isCompleted({ chatId, turnId });
  }

  /** End the local optimistic run without confirming gateway cancellation. */
  finishRunLocally(chatId: string): void {
    this.applyRunEffects(this.runs.transition({ kind: "local-stop", chatId }));
  }

  updateMaxFrameBytes(maxFrameBytes?: number): void {
    this.maxFrameBytes = this.normalizeMaxFrameBytes(maxFrameBytes);
  }

  getRunGeneration(chatId: string): number {
    return this.runs.view(chatId).generation;
  }

  hasUnsettledRun(chatId: string): boolean {
    return this.runs.view(chatId).unsettled;
  }

  onRunCompletion(handler: RunCompletionHandler): Unsubscribe {
    return this.runCompletionHandlers.subscribe(handler);
  }

  getUnsettledRunChatIds(): string[] {
    return this.runs.unresolvedChatIds().filter((chatId) => !this.temporaryChatIds.has(chatId));
  }

  private normalizeMaxFrameBytes(value: number | undefined): number | undefined {
    if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
      return undefined;
    }
    return Math.floor(value);
  }

  /** Pure preflight; it neither settles runs nor prunes queued frames. */
  canReconcileCanonicalCompletion(
    chatId: string,
    expectedRunGeneration: number,
    completedTurnIds: readonly string[],
    snapshot?: CanonicalRunSnapshot,
  ): boolean {
    return this.runs.canApplyCanonical({
      chatId, generation: expectedRunGeneration, completedTurnIds, snapshot,
    });
  }

  /** Preserve explicit completion fences even when a newer run prevents adoption. */
  reconcileCanonicalCompletion(
    chatId: string,
    expectedRunGeneration: number,
    completedTurnIds: readonly string[],
    snapshot?: CanonicalRunSnapshot,
  ): boolean {
    const result = this.runs.applyCanonical({
      chatId, generation: expectedRunGeneration, completedTurnIds, snapshot,
    });
    this.applyRunEffects(result.effects);
    return result.accepted;
  }

  fenceCanonicalCompletedTurns(chatId: string, completedTurnIds: readonly string[]): void {
    this.applyRunEffects(this.runs.transition({ kind: "fence", chatId, completedTurnIds }));
  }

  /** Last ``goal_state`` payload for *chatId*, if any frame has arrived this connection. */
  getGoalState(chatId: string): GoalStateWsPayload | undefined {
    return this.goalStateByChatId.get(chatId);
  }

  private applyRunEffects(effects: readonly RunEffect[]): void {
    for (const effect of effects) {
      switch (effect.kind) {
        case "run-status":
          this.emitRunStatus(effect.chatId, effect.state);
          break;
        case "completion":
          this.runCompletionHandlers.emit(effect.chatId);
          break;
        case "discard-send":
          this.sendQueue = this.sendQueue.filter((frame) => !(
            frame.type === "message"
            && frame.chat_id === effect.chatId
            && frame.turn_id === effect.turnId
          ));
          break;
        case "prune-inbound":
          this.transcripts.prune(effect.chatId, effect.turnIds);
          break;
        default: {
          const exhaustive: never = effect;
          return exhaustive;
        }
      }
    }
  }

  private recordGoalStateSnapshot(chatId: string, ev: InboundEvent): void {
    if (ev.event === "goal_state") {
      this.goalStateByChatId.set(chatId, ev.goal_state);
      return;
    }
    if (ev.event === "turn_end" && ev.goal_state != null && typeof ev.goal_state === "object") {
      this.goalStateByChatId.set(chatId, ev.goal_state);
    }
  }

  /** Observe live chat events without consuming transcript replay. Auto-attaches. */
  onChat(chatId: string, handler: EventHandler): Unsubscribe {
    return this.transcripts.observe(chatId, handler);
  }

  /** Own transcript delivery: consume the pending tail once, then receive live events. */
  onTranscript(chatId: string, handler: EventHandler): Unsubscribe {
    return this.transcripts.subscribe(chatId, handler);
  }

  connect(): void {
    this.connection.connect();
  }

  close(): void {
    this.connection.close();
  }

  /** Mobile browsers can leave a suspended socket looking OPEN after it has died. */
  resumeFromBackground(): Promise<void> {
    if (this.connection.closed || this.status_ === "idle" || this.status_ === "connecting") return Promise.resolve();
    if (this.foregroundCheck) return this.foregroundCheck;
    this.foregroundCheck = this.restoreForegroundConnection().finally(() => { this.foregroundCheck = null; });
    return this.foregroundCheck;
  }

  private async restoreForegroundConnection(): Promise<void> {
    const socket = this.socket;
    if (socket?.readyState === WS_OPEN) {
      try {
        await this.requestMutation("connection.check", {}, 5_000);
        if (socket !== this.socket || this.connection.closed) return;
        for (const chatId of this.knownChats) this.rawSend({ type: "attach", chat_id: chatId });
        return;
      } catch {
        if (socket !== this.socket || this.connection.closed) return;
      }
    }
    this.connection.reconnectNow(socket);
  }

  discardTemporaryChat(chatId: string): void {
    if (!this.temporaryChatIds.has(chatId)) return;
    if (this.socket?.readyState === WS_OPEN) {
      this.rawSend({ type: "discard_temporary_chat", chat_id: chatId });
    }
    this.forgetTemporaryChat(chatId);
  }

  /** Ask the server to provision a new chat_id; resolves with the assigned id. */
  newChat(timeoutMs = 5_000, workspaceScope?: WorkspaceScopePayload | null, projectId?: string | null, ptcMode = false): Promise<string> {
    return this.chatRequests.request({
      type: "new_chat",
      ...(ptcMode ? { ptc_mode: true } : {}),
      ...(projectId ? { project_id: projectId } : {}),
      ...(workspaceScope ? { workspace_scope: workspaceScope } : {}),
    }, timeoutMs, "newChat");
  }

  /** Create a connection-owned conversation without persistent history. */
  newTemporaryChat(timeoutMs = 5_000, ptcMode = false): Promise<string> {
    return this.chatRequests.request({ type: "new_temporary_chat", ...(ptcMode ? { ptc_mode: true } : {}) }, timeoutMs, "newTemporaryChat");
  }

  /**
   * Send one WebUI mutation over the authenticated socket. Pending requests are
   * replayed with the same request_id after reconnect so the gateway can join or
   * replay the original operation. A client-side timeout still ends all retries.
   */
  requestMutation<T>(action: string, payload: Record<string, unknown> = {}, timeoutMs = 20_000): Promise<T> {
    return this.mutations.request<T>(action, payload, timeoutMs);
  }

  /** Ask the server to create a non-destructive fork before a user-message index. */
  forkChat(sourceChatId: string, beforeUserIndex: number, title?: string, timeoutMs = 5_000): Promise<string> {
    return this.chatRequests.request({
      type: "fork_chat", source_chat_id: sourceChatId, before_user_index: beforeUserIndex,
      ...(title?.trim() ? { title: title.trim() } : {}),
    }, timeoutMs, "forkChat");
  }

  attach(chatId: string): void {
    if (this.temporaryChatIds.has(chatId)) return;
    this.knownChats.add(chatId);
    if (this.socket?.readyState === WS_OPEN) {
      this.queueSend({ type: "attach", chat_id: chatId });
    }
  }

  async backupRequest<T>(action: "catalog" | "export" | "upload" | "restore" | "cancel", body: Blob | Record<string, unknown> = {}): Promise<T> {
    if (!this.upload || this.socket?.readyState !== WS_OPEN) throw new Error("Reconnect to Cirno before transferring backups.");
    const url = new URL(`/v0/backups/${action}`, typeof window !== "undefined" ? window.location.href : this.currentUrl);
    const response = await fetch(url, {
      method: "POST", headers: { Authorization: `Bearer ${this.upload.token}`,
        "Content-Type": body instanceof Blob ? "application/gzip" : "application/json" },
      body: body instanceof Blob ? body : JSON.stringify(body),
    });
    const result = await response.json() as T & { error?: string };
    if (!response.ok) throw new Error(result.error || `Backup request failed (${response.status})`);
    return result;
  }

  async exportTraceRecording(recordingId: string, epoch: string): Promise<Blob> {
    if (!this.upload || this.socket?.readyState !== WS_OPEN) throw new Error("Reconnect to Cirno before exporting a recording.");
    const url = new URL("/v0/traces/export", typeof window !== "undefined" ? window.location.href : this.currentUrl);
    const response = await fetch(url, {
      method: "POST", headers: { Authorization: `Bearer ${this.upload.token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ recording_id: recordingId, epoch }),
    });
    if (!response.ok) {
      const body = response.headers.get("Content-Type")?.includes("application/json")
        ? (await response.json() as { error?: string }).error : await response.text();
      throw new Error(body || `Recording export failed (${response.status})`);
    }
    return response.blob();
  }

  async sendAttachments(
    chatId: string, content: string, media: OutboundMedia[],
    options?: Parameters<CirnoClient["sendMessage"]>[3],
  ): Promise<void> {
    const socket = this.socket;
    const capability = this.upload;
    const turnId = options?.turnId ?? crypto.randomUUID();
    const stillConnected = () => this.socket === socket
      && socket?.readyState === WS_OPEN && this.upload === capability;
    this.applyRunEffects(this.runs.transition({
      kind: "submit", chatId, turnId,
      role: options?.startsNewRun === false ? "supplement" : "candidate-owner",
    }));
    try {
      const references = await uploadAttachments(media, capability,
        typeof window !== "undefined" ? window.location.href : this.currentUrl,
        stillConnected);
      if (!stillConnected()) throw new Error("Connection changed during attachment send");
      await this.receipts.wait(turnId, () => {
        if (!this.sendMessage(chatId, content, references, { ...options, turnId })) {
          throw new Error("Message exceeds the gateway's WebSocket frame limit; draft retained");
        }
      });
    } catch (error) {
      this.applyRunEffects(this.runs.transition({ kind: "reject", chatId, turnId }));
      this.emitError({ kind: "turn_rejected", chatId, turnId, detail: "attachment_rejected",
        reason: error instanceof Error ? error.message : "Attachment send failed" });
      throw error;
    }
  }

  async sendTextMessage(
    chatId: string, content: string, options?: Parameters<CirnoClient["sendMessage"]>[3],
  ): Promise<void> {
    const turnId = options?.turnId ?? crypto.randomUUID();
    try {
      await this.receipts.wait(turnId, () => {
        if (!this.sendMessage(chatId, content, undefined, { ...options, turnId })) {
          throw new Error("Message was not sent; draft retained");
        }
      });
    } catch (error) {
      // A timed-out offline send must not reappear after the user retries it.
      this.sendQueue = this.sendQueue.filter(frame => !(frame.type === "message" && frame.turn_id === turnId));
      this.applyRunEffects(this.runs.transition({ kind: "reject", chatId, turnId }));
      this.emitError({ kind: "turn_rejected", chatId, turnId, detail: "message_rejected",
        reason: error instanceof Error ? error.message : "Message send failed" });
      throw error;
    }
  }

  async sendUserShellCommand(
    chatId: string, content: string, options?: Parameters<CirnoClient["sendMessage"]>[3],
  ): Promise<void> {
    const turnId = options?.turnId ?? crypto.randomUUID();
    try {
      await this.receipts.wait(turnId, () => {
        if (!this.sendMessage(chatId, content, undefined, { ...options, turnId, userShell: true, startsNewRun: false })) {
          throw new Error("Shell command was not sent; draft retained");
        }
      });
    } catch (error) {
      this.applyRunEffects(this.runs.transition({ kind: "reject", chatId, turnId }));
      this.emitError({ kind: "turn_rejected", chatId, turnId, detail: "message_rejected",
        reason: error instanceof Error ? error.message : "Shell command send failed" });
      throw error;
    }
  }

  sendMessage(
    chatId: string,
    content: string,
    media?: AttachmentReference[],
    options?: {
      cliApps?: OutboundCliAppMention[];
      mcpPresets?: OutboundMcpPresetMention[];
      sessionMentions?: SessionMention[];
      quotedContext?: string;
      intent?: "create_automation";
      userShell?: boolean;
      workspaceScope?: WorkspaceScopePayload | null;
      turnId?: string;
      /** False for side-channel or injected messages that do not own a lifecycle. */
      startsNewRun?: boolean;
    },
  ): boolean {
    if (options?.userShell && this.socket?.readyState !== WS_OPEN) return false;
    const temporary = this.temporaryChatIds.has(chatId);
    if (!temporary) this.knownChats.add(chatId);
    const frame: Outbound = {
      type: "message",
      chat_id: chatId,
      content,
      ...(media && media.length > 0 ? { media } : {}),
      ...(options?.cliApps?.length ? { cli_apps: options.cliApps } : {}),
      ...(options?.mcpPresets?.length ? { mcp_presets: options.mcpPresets } : {}),
      ...(options?.sessionMentions?.length
        ? { session_mentions: options.sessionMentions }
        : {}),
      ...(options?.quotedContext?.trim() ? { quoted_context: options.quotedContext.trim() } : {}),
      ...(options?.intent === "create_automation" ? { intent: options.intent } : {}),
      ...(options?.userShell ? { user_shell: true } : {}),
      ...(options?.workspaceScope ? { workspace_scope: options.workspaceScope } : {}),
      ...(options?.turnId ? { turn_id: options.turnId } : {}),
      webui: true,
    };
    if (!this.frameFitsTransport(frame)) {
      if (options?.turnId && isSystemCommandTurnId(options.turnId)) {
        this.rejectSystemCommand(options.turnId, "message_too_big");
      }
      this.emitError({
        kind: "message_too_big",
        chatId,
        ...(options?.turnId ? { turnId: options.turnId } : {}),
      });
      return false;
    }
    if (options?.turnId && !isSystemCommandTurnId(options.turnId)) {
      this.applyRunEffects(this.runs.transition({
        kind: "submit",
        chatId,
        turnId: options.turnId,
        role: options.startsNewRun === false ? "supplement" : "candidate-owner",
      }));
    }
    if (options?.userShell) return this.rawSend(frame);
    this.queueSend(frame);
    return true;
  }

  sendSystemCommand(chatId: string, command: string, timeoutMs = 5_000): Promise<void> {
    const normalized = command.trim();
    // Cancellation must reach the current connection; replaying it after a
    // reconnect could cancel a different turn submitted in the meantime.
    if ((normalized === "/stop" || normalized === "/new") && this.socket?.readyState !== WS_OPEN) {
      return Promise.reject(new Error("Connection unavailable; reconnect before stopping or clearing the conversation"));
    }
    const turnId = `${SYSTEM_COMMAND_TURN_PREFIX}${crypto.randomUUID()}`;
    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pendingSystemCommands.delete(turnId);
        reject(new Error("system command timed out"));
      }, timeoutMs);
      this.pendingSystemCommands.set(turnId, { resolve, reject, timer });
      this.sendMessage(chatId, normalized, undefined, { turnId });
    });
  }

  setWorkspaceScope(chatId: string, workspaceScope: WorkspaceScopePayload): void {
    if (this.temporaryChatIds.has(chatId)) return;
    this.knownChats.add(chatId);
    this.queueSend({
      type: "set_workspace_scope",
      chat_id: chatId,
      workspace_scope: workspaceScope,
    });
  }

  setSidebarState(state: SidebarStatePayload): Promise<SidebarStatePayload> {
    return this.requestMutation<SidebarStatePayload>("sidebar.update", { state });
  }

  // -- internals ---------------------------------------------------------

  private setStatus(status: ConnectionStatus): void {
    if (this.status_ === status) return;
    this.status_ = status;
    this.statusHandlers.emit(status);
  }

  private handleOpen(): void {
    // Re-attach every known chat_id so deliveries continue routing after a drop.
    for (const chatId of this.knownChats) {
      this.rawSend({ type: "attach", chat_id: chatId });
    }
    this.mutations.replay();
    // Flush anything queued during reconnect.
    const queued = this.sendQueue.splice(0);
    for (const frame of queued) this.rawSend(frame);
  }

  private handleMessage(ev: MessageEvent): void {
    let parsed: InboundEvent;
    try {
      parsed = JSON.parse(typeof ev.data === "string" ? ev.data : "") as InboundEvent;
      if (decodeNotification(parsed) === null) return;
    } catch {
      if (wsInboundDebugEnabled()) {
        const raw = typeof ev.data === "string" ? ev.data : String(ev.data);
        console.warn(
          "[cirno ws inbound] invalid JSON",
          raw.length > 400 ? `${raw.slice(0, 400)}… (${raw.length} chars)` : raw,
        );
      }
      return;
    }

    if (wsInboundDebugEnabled()) {
      console.log("[cirno ws inbound]", summarizeInboundWsPayload(parsed));
    }

    if (parsed.event === "webui_response") {
      this.mutations.accept(parsed);
      return;
    }

    if (parsed.event === "error") this.chatRequests.accept(parsed);
    this.receipts.event(parsed);
    const turnId = "turn_id" in parsed && typeof parsed.turn_id === "string"
      ? parsed.turn_id
      : null;
    const correlatedChatId = "chat_id" in parsed ? parsed.chat_id : undefined;
    const observation = runObservation(parsed);
    if (observation) {
      const result = this.runs.observe(observation);
      this.applyRunEffects(result.effects);
      if (result.forward === "drop") return;
      if (
        result.forward === "without-owner"
        && (parsed.event === "message_accepted" || parsed.event === "user_message")
      ) {
        parsed = { ...parsed, active_turn_id: undefined, started_at: undefined, starts_turn: false };
      }
    }
    if (parsed.event === "message_accepted") {
      if (!isSystemCommandTurnId(turnId)) {
        this.dispatch(parsed.chat_id, parsed);
      }
      return;
    }
    if (isSystemCommandTurnId(turnId)) {
      if (parsed.event === "error") {
        this.rejectSystemCommand(
          turnId,
          [parsed.detail, parsed.reason].filter(Boolean).join(":") || "server error",
        );
      } else if (parsed.event === "message" || parsed.event === "turn_end") {
        this.resolveSystemCommand(turnId);
      }
      return;
    }

    if (parsed.event === "error" && correlatedChatId && turnId) {
      if (parsed.detail !== "workspace_scope_rejected") {
        this.emitError({
          kind: "turn_rejected",
          detail: parsed.detail,
          reason: parsed.reason,
          chatId: correlatedChatId,
          turnId,
        });
      }
    }

    if (parsed.event === "ready") {
      this.upload = uploadCapability(parsed.upload);
      this.readyChatId = parsed.chat_id;
      this.knownChats.add(parsed.chat_id);
      this.readyHandlers.emit();
      return;
    }

    if (parsed.event === "attached") {
      if (parsed.temporary === true) {
        this.temporaryChatIds.add(parsed.chat_id);
      } else {
        this.knownChats.add(parsed.chat_id);
      }
      this.chatRequests.accept(parsed);
      this.dispatch(parsed.chat_id, parsed);
      return;
    }

    if (parsed.event === "runtime_model_updated") {
      this.emitRuntimeModelUpdate(parsed.model_name || null, parsed.model_preset ?? null);
      return;
    }


    if (parsed.event === "session_updated") {
      if (parsed.scope === "reset" && parsed.chat_id) {
        this.goalStateByChatId.delete(parsed.chat_id);
        this.transcripts.clearPending(parsed.chat_id);
        this.applyRunEffects(this.runs.transition({ kind: "forget", chatId: parsed.chat_id }));
      }
      this.emitSessionUpdate(parsed.chat_id, parsed.scope, parsed.workspace_scope);
      return;
    }

    if (parsed.event === "preferences_updated") {
      this.preferenceHandlers.emit(parsed.preferences);
      return;
    }

    if (parsed.event === "sidebar_state_updated") {
      this.emitSidebarStateUpdate(parsed.state);
      return;
    }

    if (parsed.event === "error" && parsed.detail === "workspace_scope_rejected") {
      this.emitError({
        kind: "workspace_scope_rejected",
        reason: parsed.reason,
        chatId: parsed.chat_id,
        turnId: parsed.turn_id,
      });
    }

    if (correlatedChatId) {
      this.recordGoalStateSnapshot(correlatedChatId, parsed);
      if ((parsed.event === "turn_end" || parsed.event === "recovery_state")
        && (this.knownChats.has(correlatedChatId) || this.temporaryChatIds.has(correlatedChatId))) {
        this.taskNoticeHandlers.emit({ event: parsed, temporary: this.temporaryChatIds.has(correlatedChatId) });
      }
      this.dispatch(correlatedChatId, parsed);
    }
  }

  private emitRuntimeModelUpdate(modelName: string | null, modelPreset?: string | null): void {
    this.runtimeModelHandlers.emit(modelName, modelPreset);
  }

  private emitSessionUpdate(
    chatId: string,
    scope?: SessionUpdateScope,
    workspaceScope?: WorkspaceScopePayload,
  ): void {
    this.sessionUpdateHandlers.emit(chatId, scope, workspaceScope);
  }

  private emitSidebarStateUpdate(state: SidebarStatePayload): void {
    this.sidebarStateUpdateHandlers.emit(state);
  }

  private emitRunStatus(chatId: string, state: RunState): void {
    this.runStatusHandlers.emit(chatId, state);
  }

  private dispatch(chatId: string, ev: InboundEvent): void {
    this.transcripts.dispatch(chatId, ev);
  }

  private handleClose(event: { code?: number } | undefined, willReconnect: boolean): void {
    this.upload = null;
    this.receipts.close();
    this.clearTemporaryChats();
    this.chatRequests.close();
    this.mutations.disconnected(willReconnect);
    for (const pending of this.pendingSystemCommands.values()) {
      clearTimeout(pending.timer);
      pending.reject(new Error("socket closed"));
    }
    this.pendingSystemCommands.clear();
    // Surface structured reasons *before* reconnect logic so the UI can
    // display the error even while the client transparently reconnects.
    // Browsers populate ``CloseEvent.code`` with the wire-level close code;
    // 1009 = Message Too Big (server's max frame guard).
    if (event?.code === 1009) {
      const rejected = this.runs.soleSentTurn(this.lastSocketMessageSend);
      if (rejected) {
        this.applyRunEffects(this.runs.transition({ kind: "reject", ...rejected }));
        this.emitError({ kind: "message_too_big", ...rejected });
        this.dispatch(rejected.chatId, {
          event: "error",
          detail: "message_too_big",
          chat_id: rejected.chatId,
          turn_id: rejected.turnId,
        });
      } else {
        // A close frame cannot identify one message among multiplexed sends.
        this.emitError({ kind: "message_too_big" });
      }
    }
    this.applyRunEffects(this.runs.transition({ kind: "transport-lost" }));
    this.lastSocketMessageSend = null;

  }

  private emitError(error: StreamError): void {
    this.errorHandlers.emit(error);
  }

  private resolveSystemCommand(turnId: string): void {
    const pending = this.pendingSystemCommands.get(turnId);
    if (!pending) return;
    clearTimeout(pending.timer);
    this.pendingSystemCommands.delete(turnId);
    pending.resolve();
  }

  private rejectSystemCommand(turnId: string, detail: string): void {
    const pending = this.pendingSystemCommands.get(turnId);
    if (!pending) return;
    clearTimeout(pending.timer);
    this.pendingSystemCommands.delete(turnId);
    pending.reject(new Error(detail));
  }

  private queueSend(frame: Outbound): void {
    if (this.socket?.readyState === WS_OPEN) {
      this.rawSend(frame);
    } else {
      this.sendQueue.push(frame);
    }
  }

  private clearTemporaryChats(): void {
    for (const chatId of [...this.temporaryChatIds]) {
      this.forgetTemporaryChat(chatId);
    }
  }

  private forgetTemporaryChat(chatId: string): void {
    this.temporaryChatIds.delete(chatId);
    this.knownChats.delete(chatId);
    this.transcripts.forget(chatId);
    const effects = this.runs.transition({ kind: "forget", chatId });
    this.goalStateByChatId.delete(chatId);
    this.sendQueue = this.sendQueue.filter((frame) => (
      !("chat_id" in frame) || frame.chat_id !== chatId
    ));
    if (this.lastSocketMessageSend?.chatId === chatId) this.lastSocketMessageSend = null;
    this.applyRunEffects(effects);
  }

  private frameFitsTransport(frame: Outbound): boolean {
    if (this.maxFrameBytes === undefined) return true;
    return new TextEncoder().encode(JSON.stringify(frame)).byteLength <= this.maxFrameBytes;
  }

  private rawSend(frame: Outbound): boolean {
    if (!this.socket) return false;
    try {
      this.socket.send(JSON.stringify(frame));
      this.lastSocketMessageSend = null;
      if (frame.type === "message" && frame.turn_id) {
        const ref = { chatId: frame.chat_id, turnId: frame.turn_id };
        if (this.runs.hasPendingSend(ref)) {
          this.applyRunEffects(this.runs.transition({ kind: "written", ...ref }));
          this.lastSocketMessageSend = ref;
        }
      }
      return true;
    } catch {
      // Shell commands require a new explicit submission, never reconnect replay.
      if (frame.type !== "message" || !frame.user_shell) this.sendQueue.push(frame);
      return false;
    }
  }


}
