import { afterEach, expect, it } from "vitest";
import { CirnoClient } from "@/lib/cirno-client";
import { FakeSocket } from "./fixtures/client-socket";

const clients: CirnoClient[] = [];
afterEach(() => { clients.splice(0).forEach(client => client.close()); });

function connected(maxFrameBytes?: number) {
  const client = new CirnoClient({ url: "ws://fixture", reconnect: false, maxFrameBytes,
    socketFactory: url => new FakeSocket(url) as unknown as WebSocket });
  clients.push(client);
  client.connect();
  const socket = FakeSocket.instances.at(-1)!;
  socket.fakeOpen();
  return { client, socket };
}

it.each([undefined, 100_000])("rejects unencodable payloads as a promise with frame limit %s", async limit => {
  const { client, socket } = connected(limit);
  const payload: Record<string, unknown> = {};
  payload.self = payload;
  await expect(client.requestMutation("fixture.save", payload)).rejects.toMatchObject({ status: 503 });
  expect(socket.sent).toEqual([]);
});

it("measures and sends the same single serialization of a mutation", async () => {
  const { client, socket } = connected(100_000);
  let reads = 0;
  const payload = { get value() { reads += 1; return reads; } };
  const pending = client.requestMutation("fixture.save", payload);
  const frame = JSON.parse(socket.sent[0]);
  socket.fakeMessage({ event: "webui_response", request_id: frame.request_id, ok: true, result: "saved" });
  await expect(pending).resolves.toBe("saved");
  expect(reads).toBe(1);
  expect(frame.payload).toEqual({ value: 1 });
});
