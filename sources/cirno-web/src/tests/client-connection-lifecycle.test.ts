import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CirnoClient } from "@/lib/cirno-client";
import { FakeSocket } from "./fixtures/client-socket";

beforeEach(() => { FakeSocket.instances = []; vi.useFakeTimers(); });
afterEach(() => { vi.useRealTimers(); });

it("does not reopen a disposed client when a pending authorization refresh finishes", async () => {
  let authorize!: (url: string) => void;
  const refresh = new Promise<string>((resolve) => { authorize = resolve; });
  const reauth = vi.fn(() => refresh);
  const client = new CirnoClient({ url: "ws://fixture", onReauth: reauth,
    socketFactory: (url) => new FakeSocket(url) as unknown as WebSocket });
  try {
    client.connect();
    const first = FakeSocket.instances[0];
    first.fakeOpen();
    first.close();
    await vi.advanceTimersByTimeAsync(500);
    expect(reauth).toHaveBeenCalledOnce();
    client.close();
    authorize("ws://refreshed");
    await vi.advanceTimersByTimeAsync(0);
    expect(FakeSocket.instances).toHaveLength(1);
    expect(client.status).toBe("closed");
  } finally { client.close(); }
});

it("ignores frames and close callbacks retained by a replaced socket", () => {
  const client = new CirnoClient({ url: "ws://fixture",
    socketFactory: (url) => new FakeSocket(url) as unknown as WebSocket });
  try {
    client.connect();
    const first = FakeSocket.instances[0];
    first.fakeOpen();
    const delayedMessage = first.onmessage!;
    const delayedClose = first.onclose!;
    client.close();
    client.connect();
    const second = FakeSocket.instances[1];
    second.fakeOpen();
    second.fakeMessage({ event: "ready", chat_id: "current" });
    delayedMessage({ data: JSON.stringify({ event: "ready", chat_id: "stale" }) } as MessageEvent);
    delayedClose();
    expect(client.defaultChatId).toBe("current");
    expect(client.status).toBe("open");
    client.attach("worker");
    expect(JSON.parse(second.sent.at(-1)!)).toMatchObject({ type: "attach", chat_id: "worker" });
  } finally { client.close(); }
});
