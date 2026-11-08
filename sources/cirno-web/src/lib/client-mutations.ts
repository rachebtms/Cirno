import type { InboundEvent } from "./contracts/events";
import type { Outbound } from "./contracts/transport";

type MutationResponse = Extract<InboundEvent, { event: "webui_response" }>;
interface PendingMutation {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
  frame: string;
}

class WebUIMutationError extends Error {
  constructor(readonly status: number, message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "WebUIMutationError";
  }
}

/** Own correlated mutation requests and their original replay deadline/frame. */
export class ClientMutations {
  private pending = new Map<string, PendingMutation>();

  constructor(
    private socket: () => WebSocket | null,
    private byteLimit: () => number | undefined,
  ) {}

  request<T>(action: string, payload: Record<string, unknown>, timeoutMs: number): Promise<T> {
    const socket = this.socket();
    if (!socket || socket.readyState !== 1) {
      return Promise.reject(new WebUIMutationError(503, "WebUI connection is not open"));
    }
    const id = crypto.randomUUID();
    const envelope: Outbound = { type: "webui_request", request_id: id, action, payload };
    let frame: string;
    try {
      frame = JSON.stringify(envelope);
    } catch (error) {
      return Promise.reject(new WebUIMutationError(503, "Could not encode WebUI request", { cause: error }));
    }
    const limit = this.byteLimit();
    if (limit !== undefined && new TextEncoder().encode(frame).byteLength > limit) {
      return Promise.reject(new WebUIMutationError(413, "WebUI mutation payload is too large"));
    }
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new WebUIMutationError(504, `WebUI request timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pending.set(id, { resolve: value => resolve(value as T), reject, timer, frame });
      try {
        socket.send(frame);
      } catch (error) {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(new WebUIMutationError(503, "Could not send WebUI request", { cause: error }));
      }
    });
  }

  accept(response: MutationResponse): void {
    const request = this.pending.get(response.request_id);
    if (!request) return;
    clearTimeout(request.timer);
    this.pending.delete(response.request_id);
    if (response.ok) {
      request.resolve(response.result);
    } else {
      request.reject(new WebUIMutationError(
        Number.isFinite(response.error?.status) ? response.error.status : 500,
        response.error?.message || "WebUI mutation failed",
      ));
    }
  }

  replay(): void {
    for (const request of this.pending.values()) {
      const socket = this.socket();
      if (!socket) return;
      try {
        socket.send(request.frame);
      } catch (error) {
        // The accepted request keeps its original deadline and ID for reconnect.
        console.warn("Could not replay WebUI request", error);
      }
    }
  }

  disconnected(willReconnect: boolean): void {
    if (willReconnect) return;
    for (const request of this.pending.values()) {
      clearTimeout(request.timer);
      request.reject(new WebUIMutationError(503, "Socket closed before WebUI response"));
    }
    this.pending.clear();
  }
}
