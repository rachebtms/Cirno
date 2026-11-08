import type { InboundEvent } from "./contracts/events";
import { ClientListeners } from "./client-listeners";

type Handler = (event: InboundEvent) => void;
const PENDING_MAX = 2000;

/** One transcript owner consumes replay; independent observers receive live events. */
export class ClientTranscripts {
  private readonly observers = new Map<string, ClientListeners<[InboundEvent]>>();
  private readonly owners = new Map<string, { handler: Handler }>();
  private readonly pending = new Map<string, InboundEvent[]>();
  constructor(private readonly attach: (chatId: string) => void,
    private readonly temporary: (chatId: string) => boolean) {}

  observe(chatId: string, handler: Handler): () => void {
    let group = this.observers.get(chatId);
    if (!group) {
      group = new ClientListeners("chat observer");
      this.observers.set(chatId, group);
    }
    const unsubscribe = group.subscribe(handler);
    this.attach(chatId);
    return () => {
      unsubscribe();
      if (group.size === 0 && this.observers.get(chatId) === group) this.observers.delete(chatId);
    };
  }

  subscribe(chatId: string, handler: Handler): () => void {
    if (this.owners.has(chatId)) throw new Error(`Transcript already subscribed: ${chatId}`);
    const subscription = { handler };
    this.owners.set(chatId, subscription);
    const pending = this.pending.get(chatId) ?? [];
    this.pending.delete(chatId);
    let consumed = 0;
    try {
      for (const event of pending) { handler(event); consumed++; }
    } catch (error) {
      if (this.owners.get(chatId) === subscription) {
        this.owners.delete(chatId);
        this.pending.set(chatId, pending.slice(consumed));
      }
      throw error;
    }
    this.attach(chatId);
    return () => {
      if (this.owners.get(chatId) === subscription) this.owners.delete(chatId);
    };
  }

  dispatch(chatId: string, event: InboundEvent): void {
    const owner = this.owners.get(chatId);
    if (owner) owner.handler(event);
    else {
      const pending = this.pending.get(chatId) ?? [];
      pending.push(event);
      // A temporary transcript has no persisted history to recover an evicted tail.
      if (!this.temporary(chatId) && pending.length > PENDING_MAX) pending.splice(0, pending.length - PENDING_MAX);
      this.pending.set(chatId, pending);
    }
    this.observers.get(chatId)?.emit(event);
  }

  prune(chatId: string, turnIds: readonly string[]): void {
    const pending = this.pending.get(chatId);
    if (!pending) return;
    const completed = new Set(turnIds);
    const remaining = pending.filter(event => !("turn_id" in event)
      || typeof event.turn_id !== "string" || !completed.has(event.turn_id));
    if (remaining.length > 0) this.pending.set(chatId, remaining);
    else this.pending.delete(chatId);
  }

  clearPending(chatId: string): void { this.pending.delete(chatId); }
  forget(chatId: string): void {
    this.observers.delete(chatId);
    this.owners.delete(chatId);
    this.pending.delete(chatId);
  }
}
