import { afterEach, expect, it } from "vitest";
import { CirnoClient } from "@/lib/cirno-client";
import { FakeSocket } from "./fixtures/client-socket";

const clients: CirnoClient[] = [];
afterEach(() => { clients.splice(0).forEach(client => client.close()); FakeSocket.instances = []; });
function connection() {
  const client = new CirnoClient({ url: "ws://fixture", reconnect: false,
    socketFactory: url => new FakeSocket(url) as unknown as WebSocket });
  clients.push(client); client.connect();
  const socket = FakeSocket.instances.at(-1)!; socket.fakeOpen();
  return { client, socket };
}
function notice(socket: FakeSocket, id: string, turnId?: string) {
  socket.fakeMessage({ event: "user_message", chat_id: "worker", text: "Goal stopped; progress retained.",
    starts_turn: false, ...(turnId ? { turn_id: turnId } : {}),
    provenance: { session_message: { message_id: id, session: { id: "router", name: "cirno" } },
      input_origin: { kind: "supervision", label: "@cirno", id, action: "goal.stop" } } });
}

it.each([false, true])("passive Router notices do not start an idle run, locally stopped=%s", stopped => {
  const { client, socket } = connection();
  const received: unknown[] = [];
  client.onTranscript("worker", event => received.push(event));
  if (stopped) {
    socket.fakeMessage({ event: "goal_status", chat_id: "worker", turn_id: "old", status: "running", started_at: 100 });
    client.finishRunLocally("worker");
  }
  expect(client.getRunState("worker").active).toBe(false);
  notice(socket, "stop-record");
  expect(client.getRunState("worker").active).toBe(false);
  expect(client.hasUnsettledRun("worker")).toBe(false);
  expect(received.some(event => (event as { event: string }).event === "user_message")).toBe(true);
  notice(socket, "another-record", "audit-only");
  expect(client.getRunState("worker").active).toBe(false);
});

it("a Goal status or passive notice cannot settle genuine execution before its terminal event", () => {
  const { client, socket } = connection();
  socket.fakeMessage({ event: "goal_status", chat_id: "worker", turn_id: "live", status: "running", started_at: 100 });
  socket.fakeMessage({ event: "goal_state", chat_id: "worker", goal_state: { active: false, status: "stopped" } });
  notice(socket, "stop-record");
  expect(client.getRunState("worker").active).toBe(true);
  expect(client.getRunTurnId("worker")).toBe("live");
  socket.fakeMessage({ event: "turn_end", chat_id: "worker", turn_id: "live" });
  socket.fakeMessage({ event: "goal_status", chat_id: "worker", turn_id: "live", status: "idle" });
  notice(socket, "stopped-final-record");
  expect(client.getRunState("worker").active).toBe(false);
  socket.fakeMessage({ event: "user_message", chat_id: "worker", turn_id: "next", text: "New authorized task", starts_turn: true, active_turn_id: "next", started_at: 200 });
  expect(client.getRunState("worker").active).toBe(true);
  expect(client.getRunTurnId("worker")).toBe("next");
});

it("quiet heartbeat and Worker-report turns settle without a visible reply", () => {
  const { client, socket } = connection();
  for (const turnId of ["heartbeat-1", "worker-report-1", "heartbeat-2"]) {
    socket.fakeMessage({ event: "goal_status", chat_id: "router", turn_id: turnId, status: "running", started_at: 100 });
    socket.fakeMessage({ event: "reasoning_delta", chat_id: "router", turn_id: turnId, text: "No update needed." });
    expect(client.getRunState("router").active).toBe(true);
    socket.fakeMessage({ event: "turn_end", chat_id: "router", turn_id: turnId });
    socket.fakeMessage({ event: "goal_status", chat_id: "router", turn_id: turnId, status: "idle" });
    expect(client.getRunState("router").active).toBe(false);
    expect(client.hasUnsettledRun("router")).toBe(false);
    // A delayed tail from this closed request must not restart Working.
    socket.fakeMessage({ event: "stream_end", chat_id: "router", turn_id: turnId });
    expect(client.getRunState("router").active).toBe(false);
  }
});

it("automatic slices retain one run until its final completion", () => {
  const { client, socket } = connection();
  for (let slice = 0; slice < 4; slice++) {
    socket.fakeMessage({ event: "goal_status", chat_id: "worker", turn_id: "goal-turn", status: "running", started_at: 100 });
    socket.fakeMessage({ event: "stream_end", chat_id: "worker", turn_id: "goal-turn" });
    expect(client.getRunState("worker").active).toBe(true);
  }
  socket.fakeMessage({ event: "turn_end", chat_id: "worker", turn_id: "goal-turn" });
  socket.fakeMessage({ event: "goal_status", chat_id: "worker", turn_id: "goal-turn", status: "idle" });
  expect(client.getRunState("worker").active).toBe(false);
  expect(client.hasUnsettledRun("worker")).toBe(false);
});
