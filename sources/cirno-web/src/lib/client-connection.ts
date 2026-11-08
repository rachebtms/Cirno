import type { ConnectionStatus } from "./contracts/transport";

export interface ClientConnectionOptions {
  url: string;
  reconnect?: boolean;
  onReauth?: () => Promise<string | null>;
  socketFactory?: (url: string) => WebSocket;
  maxBackoffMs?: number;
}

interface ConnectionEvents {
  status: (status: ConnectionStatus) => void;
  opened: () => void;
  message: (event: MessageEvent) => void;
  closed: (event: { code?: number } | undefined, willReconnect: boolean) => void;
}

/** Own sockets and reconnect work; callbacks belong to one connection generation. */
export class ClientConnection {
  socket: WebSocket | null = null;
  url: string;
  closed = false;
  readonly reconnectEnabled: boolean;
  private epoch = 0;
  private attempts = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private factory: (url: string) => WebSocket;

  constructor(private options: ClientConnectionOptions, private events: ConnectionEvents) {
    this.url = options.url;
    this.factory = options.socketFactory ?? ((url) => new WebSocket(url));
    this.reconnectEnabled = options.reconnect ?? true;
  }

  updateUrl(url: string, factory?: (url: string) => WebSocket): void {
    this.url = url;
    if (factory) this.factory = factory;
  }

  connect(): void {
    if (this.socket && this.socket.readyState < 2) return;
    this.cancelTimer();
    this.closed = false;
    const epoch = ++this.epoch;
    this.events.status("connecting");
    const socket = this.factory(this.url);
    this.socket = socket;
    const current = () => epoch === this.epoch && socket === this.socket;
    socket.onopen = () => {
      if (!current()) return;
      this.attempts = 0;
      this.events.status("open");
      this.events.opened();
    };
    socket.onmessage = (event) => { if (current()) this.events.message(event); };
    socket.onerror = () => { if (current()) this.events.status("error"); };
    socket.onclose = (event) => { if (current()) this.lost(event); };
  }

  close(): void {
    this.closed = true;
    this.cancelTimer();
    ++this.epoch;
    const socket = this.socket;
    this.socket = null;
    try {
      socket?.close();
    } finally {
      this.lost();
    }
  }

  reconnectNow(expected: WebSocket | null): void {
    if (!this.reconnectEnabled || this.closed || expected !== this.socket) return;
    this.cancelTimer();
    ++this.epoch;
    this.socket = null;
    try {
      expected?.close();
    } finally {
      this.lost(undefined, 0);
    }
  }

  private lost(event?: { code?: number }, delay?: number): void {
    this.socket = null;
    const willReconnect = !this.closed && this.reconnectEnabled;
    try {
      this.events.closed(event, willReconnect);
    } finally {
      if (willReconnect) this.scheduleReconnect(delay);
      else this.events.status("closed");
    }
  }

  private cancelTimer(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }

  private scheduleReconnect(delay?: number): void {
    this.cancelTimer();
    this.events.status("reconnecting");
    const epoch = this.epoch;
    const wait = delay ?? Math.min(500 * 2 ** this.attempts++, this.options.maxBackoffMs ?? 15_000);
    this.timer = setTimeout(async () => {
      this.timer = null;
      const url = this.url;
      let refreshed: string | null = null;
      if (this.options.onReauth) {
        try {
          refreshed = await this.options.onReauth();
        } catch (error) {
          console.warn("Connection authorization refresh failed", error);
        }
      }
      if (this.closed || epoch !== this.epoch) return;
      if (refreshed && this.url === url) this.url = refreshed;
      this.connect();
    }, wait);
  }
}
