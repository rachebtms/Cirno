import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CirnoClient } from "@/lib/cirno-client";
import { FakeSocket } from "./fixtures/client-socket";
let client: CirnoClient;
beforeEach(() => {
  vi.useFakeTimers();
  client = new CirnoClient({ url: "ws://fixture", reconnect: false,
    socketFactory: url => new FakeSocket(url) as unknown as WebSocket });
  client.connect();
});
afterEach(() => { client.close(); vi.clearAllTimers(); vi.useRealTimers(); });

it.each(["attached", "error"])("does not settle chat creation with an unrelated %s event", async kind => {
  const socket = FakeSocket.instances.at(-1)!;
  socket.fakeOpen();
  client.attach("existing");
  let settled = false;
  const pending = client.newChat();
  pending.then(() => { settled = true; }, () => { settled = true; });
  const request = JSON.parse(socket.sent.at(-1)!);
  socket.fakeMessage(kind === "attached"
    ? { event: "attached", chat_id: "existing" }
    : { event: "error", chat_id: "existing", turn_id: "existing-turn", detail: "Fixture worker failed" });
  await Promise.resolve();
  expect(settled).toBe(false);
  socket.fakeMessage({ event: "attached", chat_id: "created", request_id: request.request_id });
  await expect(pending).resolves.toBe("created");
});

it("removes a timed-out creation from the offline queue before reconnect", async () => {
  const socket = FakeSocket.instances.at(-1)!;
  const rejected = expect(client.newChat(25)).rejects.toThrow("timed out");
  await vi.advanceTimersByTimeAsync(25);
  await rejected;
  socket.fakeOpen();
  expect(socket.sent.map(frame => JSON.parse(frame).type)).not.toContain("new_chat");
});

it("does not let a late creation reply settle a newer creation", async () => {
  const socket = FakeSocket.instances.at(-1)!;
  socket.fakeOpen();
  const expired = expect(client.newChat(25)).rejects.toThrow("timed out");
  const oldId = socket.creationRequestId();
  await vi.advanceTimersByTimeAsync(25);
  await expired;
  const current = client.newChat();
  let settled = false;
  current.then(() => { settled = true; }, () => { settled = true; });
  socket.fakeMessage({ event: "attached", chat_id: "old-result", request_id: oldId });
  await Promise.resolve();
  expect(settled).toBe(false);
  socket.fakeCreated("current-result");
  await expect(current).resolves.toBe("current-result");
});

it("correlates a fork with its source boundary and server-assigned conversation", async () => {
  const socket = FakeSocket.instances.at(-1)!;
  socket.fakeOpen();
  const created = client.forkChat("source", 3, "Research fork");
  const frame = JSON.parse(socket.sent.at(-1)!);
  expect(frame).toMatchObject({ type: "fork_chat", source_chat_id: "source", before_user_index: 3, title: "Research fork", request_id: expect.any(String) });
  socket.fakeCreated("fork-result");
  await expect(created).resolves.toBe("fork-result");
});
