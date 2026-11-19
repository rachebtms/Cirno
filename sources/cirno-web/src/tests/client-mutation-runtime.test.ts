import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ClientMutations } from "@/lib/client-mutations";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function connection() {
  const socket = { readyState: 1, send: vi.fn() };
  const mutations = new ClientMutations(() => socket as unknown as WebSocket, () => undefined);
  return { socket, mutations };
}

it("waits for a server-budgeted Node command without a second client deadline", async () => {
  const { socket, mutations } = connection();
  const pending = mutations.request("instance.action", { action: "nodes.execute" }, 0);
  let settled = false;
  void pending.then(() => { settled = true; });
  await vi.advanceTimersByTimeAsync(3_600_000);
  expect(settled).toBe(false);
  expect(socket.send).toHaveBeenCalledTimes(1);
  const frame = socket.send.mock.calls[0][0];
  mutations.accept({ event: "webui_response", request_id: JSON.parse(frame).request_id, ok: true, result: { exit_code: 0 } });
  await expect(pending).resolves.toEqual({ exit_code: 0 });
  mutations.replay();
  expect(socket.send).toHaveBeenCalledTimes(1);
});

it("does not resubmit an unconfirmed Node command after reconnect or cache expiry", async () => {
  const { socket, mutations } = connection();
  const pending = expect(mutations.request("instance.action", { action: "nodes.execute" }, 0))
    .rejects.toMatchObject({ status: 503, message: expect.stringContaining("inspect the remote effects before retrying") });
  mutations.disconnected(true);
  await pending;
  await vi.advanceTimersByTimeAsync(3_600_000);
  mutations.replay();
  expect(socket.send).toHaveBeenCalledTimes(1);
});

it("settles a no-deadline request when the connection is permanently closed", async () => {
  const { mutations } = connection();
  const pending = expect(mutations.request("instance.action", { action: "nodes.execute" }, 0))
    .rejects.toMatchObject({ status: 503 });
  mutations.disconnected(false);
  await pending;
  expect(vi.getTimerCount()).toBe(0);
});

it("retains finite deadlines for other mutations", async () => {
  const { socket, mutations } = connection();
  const pending = expect(mutations.request("settings.save", {}, 25)).rejects.toMatchObject({ status: 504 });
  await vi.advanceTimersByTimeAsync(25);
  await pending;
  mutations.replay();
  expect(socket.send).toHaveBeenCalledTimes(1);
});
