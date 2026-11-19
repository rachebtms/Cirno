import { uploadAttachments, type AttachmentReference, type UploadCapability } from "../../packages/client-events/attachments";
import { DeliveryReceipts } from "../../packages/client-events/delivery";
import type { InboundEvent } from "./contracts/events";
import type { OutboundCliAppMention, OutboundMcpPresetMention, OutboundMedia, SessionMention } from "./contracts/messages";
import type { WorkspaceScopePayload } from "./contracts/workspaces";

export interface MessageSendOptions {
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
}

interface DeliveryPort {
  socket: () => WebSocket | null;
  upload: () => UploadCapability | null;
  baseUrl: () => string;
  send: (chatId: string, content: string, media: AttachmentReference[] | undefined, options: MessageSendOptions) => boolean;
  submit: (chatId: string, turnId: string, startsNewRun: boolean) => void;
  reject: (chatId: string, turnId: string, detail: string, reason: string) => void;
  discardQueued: (turnId: string) => void;
}

interface FailurePolicy {
  detail: "message_rejected" | "attachment_rejected";
  fallbackReason: string;
  discardQueued?: boolean;
}

/** Own one acceptance receipt and rejection path for text, shell and attachments. */
export class ClientMessageDelivery {
  private readonly receipts = new DeliveryReceipts();

  constructor(private readonly port: DeliveryPort) {}

  accept(event: InboundEvent): void { this.receipts.event(event); }
  close(): void { this.receipts.close(); }

  async attachments(chatId: string, content: string, media: OutboundMedia[], options?: MessageSendOptions): Promise<void> {
    const socket = this.port.socket();
    const capability = this.port.upload();
    const turnId = options?.turnId ?? crypto.randomUUID();
    const stillConnected = () => this.port.socket() === socket
      && socket?.readyState === 1 && this.port.upload() === capability;
    this.port.submit(chatId, turnId, options?.startsNewRun !== false);
    return this.withFailureReceipt(chatId, turnId, {
      detail: "attachment_rejected", fallbackReason: "Attachment send failed",
    }, async () => {
      const references = await uploadAttachments(media, capability, this.port.baseUrl(), stillConnected);
      if (!stillConnected()) throw new Error("Connection changed during attachment send");
      await this.receipts.wait(turnId, () => {
        if (!this.port.send(chatId, content, references, { ...options, turnId })) {
          throw new Error("Message exceeds the gateway's WebSocket frame limit; draft retained");
        }
      });
    });
  }

  async text(chatId: string, content: string, options?: MessageSendOptions): Promise<void> {
    const turnId = options?.turnId ?? crypto.randomUUID();
    return this.withFailureReceipt(chatId, turnId, {
      detail: "message_rejected", fallbackReason: "Message send failed", discardQueued: true,
    }, () => this.receipts.wait(turnId, () => {
      if (!this.port.send(chatId, content, undefined, { ...options, turnId })) {
        throw new Error("Message was not sent; draft retained");
      }
    }));
  }

  async shell(chatId: string, content: string, options?: MessageSendOptions): Promise<void> {
    const turnId = options?.turnId ?? crypto.randomUUID();
    return this.withFailureReceipt(chatId, turnId, {
      detail: "message_rejected", fallbackReason: "Shell command send failed",
    }, () => this.receipts.wait(turnId, () => {
      if (!this.port.send(chatId, content, undefined, { ...options, turnId, userShell: true, startsNewRun: false })) {
        throw new Error("Shell command was not sent; draft retained");
      }
    }));
  }

  private async withFailureReceipt(
    chatId: string, turnId: string, failure: FailurePolicy, operation: () => Promise<void>,
  ): Promise<void> {
    try {
      await operation();
    } catch (error) {
      // Offline text must not reappear after its retained draft has been retried.
      if (failure.discardQueued) this.port.discardQueued(turnId);
      this.port.reject(chatId, turnId, failure.detail,
        error instanceof Error ? error.message : failure.fallbackReason);
      throw error;
    }
  }
}
