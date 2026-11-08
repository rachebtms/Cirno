/**
 * Minimal fake WebSocket implementing the subset CirnoClient touches.
 * Every instance is retrievable via ``FakeSocket.instances`` so tests can
 * drive open/close/message lifecycles deterministically.
 */
export class FakeSocket {
  static instances: FakeSocket[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  url: string;
  readyState = FakeSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((ev?: { code?: number }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = FakeSocket.CLOSED;
    this.onclose?.();
  }

  /** Simulate a server-initiated drop with a specific wire-level close code
   * (e.g. ``1009`` for Message Too Big). */
  fakeCloseWithCode(code: number) {
    this.readyState = FakeSocket.CLOSED;
    this.onclose?.({ code });
  }

  fakeOpen() {
    this.readyState = FakeSocket.OPEN;
    this.onopen?.();
  }

  creationRequestId(): string {
    const frame = [...this.sent].reverse().map(raw => JSON.parse(raw)).find(frame =>
      ["new_chat", "new_temporary_chat", "fork_chat"].includes(frame.type));
    if (!frame || typeof frame.request_id !== "string") throw new Error("No correlated creation request");
    return frame.request_id;
  }

  fakeCreated(chatId: string): void {
    const frame = [...this.sent].reverse().map(raw => JSON.parse(raw)).find(frame =>
      ["new_chat", "new_temporary_chat", "fork_chat"].includes(frame.type));
    this.fakeMessage({ event: "attached", chat_id: chatId, request_id: this.creationRequestId(),
      ...(frame.type === "new_temporary_chat" ? { temporary: true } : {}) });
  }

  fakeMessage(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
}
