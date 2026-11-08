import type { InboundEvent } from "./contracts/events";
import type { Outbound } from "./contracts/transport";

type Creation = Extract<Outbound, { type: "new_chat" | "new_temporary_chat" | "fork_chat" }>;
type Response = Extract<InboundEvent, { event: "attached" | "error" }>;
interface PendingCreation {
  id: string;
  temporary: boolean;
  finish: (error?: Error, chatId?: string) => void;
}

/** A creation owns its response ID, deadline and any unsent queued command. */
export class ClientChatRequests {
  private pending: PendingCreation | null = null;
  constructor(private send: (frame: Outbound) => void, private discard: (id: string) => void) {}

  request(command: Creation, timeoutMs: number, label: string): Promise<string> {
    if (this.pending) return Promise.reject(new Error("newChat already in flight"));
    const id = crypto.randomUUID();
    return new Promise<string>((resolve, reject) => {
      const finish = (error?: Error, chatId?: string) => {
        clearTimeout(timer);
        this.discard(id);
        this.pending = null;
        if (error) reject(error); else resolve(chatId!);
      };
      const timer = setTimeout(() => finish(new Error(`${label} timed out`)), timeoutMs);
      this.pending = { id, temporary: command.type === "new_temporary_chat", finish };
      try { this.send({ ...command, request_id: id }); }
      catch (error) { finish(error instanceof Error ? error : new Error(String(error))); }
    });
  }

  accept(response: Response): void {
    const pending = this.pending;
    if (!pending || response.request_id !== pending.id) return;
    if (response.event === "error") {
      const reason = [response.detail || "server error", response.reason].filter(Boolean).join(":");
      pending.finish(new Error(reason));
    } else if (pending.temporary !== (response.temporary === true)) {
      pending.finish(new Error("Conversation creation returned an unexpected conversation type"));
    } else {
      pending.finish(undefined, response.chat_id);
    }
  }

  close(): void { this.pending?.finish(new Error("socket closed")); }
}
