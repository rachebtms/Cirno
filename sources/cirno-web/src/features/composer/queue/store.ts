import { pauseQueuedPrompt, queuedPromptAuthorization, type QueuedPrompt } from "../contracts";
import { readQueuedPrompt, storeQueuedPrompt } from "./storage";

type SendIssue = { kind: "rejected" } | { kind: "error"; detail: string };
interface StorageIssue { action: "read" | "save"; detail: string }
export interface QueuedPromptSnapshot {
  prompt: QueuedPrompt | null;
  sending: boolean;
  error: SendIssue | null;
  storageIssue: StorageIssue | null;
}
const stores = new Map<string, QueuedPromptStore>();
const detail = (error: unknown) => error instanceof Error ? error.message : String(error);

/** Own a waiting message until transport acceptance and durable local removal. */
export class QueuedPromptStore {
  private snapshot: QueuedPromptSnapshot = { prompt: null, sending: false, error: null, storageIssue: null };
  private listeners = new Set<() => void>();
  private restorePending = false;
  constructor(private storageKey: string | null) {
    if (!storageKey) return;
    this.restorePending = true;
    this.retryStorage();
  }
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => {
    if (this.storageKey) stores.set(this.storageKey, this);
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); this.release(); };
  };
  private release() {
    if (this.storageKey && !this.snapshot.sending && !this.snapshot.storageIssue &&
        !this.listeners.size && stores.get(this.storageKey) === this) stores.delete(this.storageKey);
  }
  private notify() { for (const listener of this.listeners) listener(); this.release(); }
  private publish(next: QueuedPromptSnapshot) {
    if (this.storageKey && next.prompt !== this.snapshot.prompt) {
      this.restorePending = false;
      try {
        storeQueuedPrompt(this.storageKey, next.prompt);
        next = { ...next, storageIssue: null };
      } catch (error) {
        next = { ...next, storageIssue: { action: "save", detail: detail(error) } };
      }
    }
    this.snapshot = next;
    this.notify();
  }
  retryStorage = () => {
    if (!this.storageKey || this.snapshot.sending) return;
    const action = this.restorePending ? "read" : "save";
    try {
      const prompt = this.restorePending ? readQueuedPrompt(this.storageKey) : this.snapshot.prompt;
      if (!this.restorePending) storeQueuedPrompt(this.storageKey, prompt);
      this.restorePending = false;
      this.snapshot = { ...this.snapshot, prompt, storageIssue: null };
    } catch (error) {
      this.snapshot = { ...this.snapshot, storageIssue: { action, detail: detail(error) } };
    }
    this.notify();
  };
  set = (next: QueuedPrompt | null | ((current: QueuedPrompt | null) => QueuedPrompt | null)) => {
    const prompt = typeof next === "function" ? next(this.snapshot.prompt) : next;
    if (prompt !== this.snapshot.prompt) this.publish({ ...this.snapshot, prompt, error: null });
  };
  reportError = (message: string) => this.publish({ ...this.snapshot, error: { kind: "error", detail: message } });
  send(prompt: QueuedPrompt, send: () => void | boolean | Promise<void | boolean>) {
    if (this.snapshot.sending) return;
    const retained = pauseQueuedPrompt(prompt);
    this.publish({ ...this.snapshot, prompt: retained, sending: true, error: null });
    const finish = (accepted: void | boolean, error?: unknown) => {
      const failed = accepted === false || error !== undefined;
      this.publish({ ...this.snapshot, prompt: failed ? retained : null, sending: false,
        error: failed ? error === undefined ? { kind: "rejected" } : { kind: "error", detail: detail(error) } : null });
    };
    try {
      const result = send();
      if (result instanceof Promise) void result.then(accepted => finish(accepted), error => finish(false, error));
      else finish(result);
    } catch (error) { finish(false, error); }
  }
}
export function queuedPromptStoreFor(storageKey: string | null): QueuedPromptStore {
  if (!storageKey) return new QueuedPromptStore(null);
  const existing = stores.get(storageKey);
  if (existing) return existing;
  const store = new QueuedPromptStore(storageKey);
  stores.set(storageKey, store);
  return store;
}
export function expireQueuedPromptAuthorization(): void {
  queuedPromptAuthorization.pageId = undefined;
  for (const store of stores.values()) store.set(prompt => prompt && !prompt.autoPaused ? pauseQueuedPrompt(prompt) : prompt);
}
if (typeof window !== "undefined") {
  window.addEventListener("pagehide", expireQueuedPromptAuthorization);
  document.addEventListener("freeze", expireQueuedPromptAuthorization);
}
