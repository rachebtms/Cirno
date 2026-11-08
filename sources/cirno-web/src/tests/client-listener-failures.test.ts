import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CirnoClient } from "@/lib/cirno-client";
import { FakeSocket } from "./fixtures/client-socket";

beforeEach(() => { FakeSocket.instances = []; });
afterEach(() => { vi.restoreAllMocks(); });

function connected() {
  const client = new CirnoClient({ url: "ws://fixture", reconnect: false,
    socketFactory: url => new FakeSocket(url) as unknown as WebSocket });
  client.connect();
  return { client, socket: FakeSocket.instances[0] };
}

it("a completion observer failure does not lose the terminal transcript event", () => {
  const { client, socket } = connected();
  const diagnostic = vi.spyOn(console, "error").mockImplementation(() => {});
  const failure = new Error("completion view failed");
  const transcript = vi.fn(), completed = vi.fn();
  try {
    socket.fakeOpen();
    client.onTranscript("worker", transcript);
    socket.fakeMessage({ event: "goal_status", chat_id: "worker", turn_id: "run", status: "running", started_at: 100 });
    client.onRunCompletion(() => { throw failure; });
    client.onRunCompletion(completed);
    const end = { event: "turn_end", chat_id: "worker", turn_id: "run", outcome: "completed" };
    expect(() => socket.fakeMessage(end)).not.toThrow();
    expect(completed).toHaveBeenCalledWith("worker");
    expect(transcript).toHaveBeenCalledWith(end);
    expect(client.hasUnsettledRun("worker")).toBe(false);
    expect(diagnostic).toHaveBeenCalledWith(expect.stringContaining("completion"), failure);
  } finally { client.close(); }
});

it("a status observer failure does not prevent flushing a queued creation", async () => {
  const { client, socket } = connected();
  const diagnostic = vi.spyOn(console, "error").mockImplementation(() => {});
  const failure = new Error("connection badge failed");
  client.onStatus(status => { if (status === "open") throw failure; });
  const creation = client.newChat();
  try {
    expect(() => socket.fakeOpen()).not.toThrow();
    expect(socket.creationRequestId()).toEqual(expect.any(String));
    socket.fakeCreated("created");
    await expect(creation).resolves.toBe("created");
    expect(diagnostic).toHaveBeenCalledWith(expect.stringContaining("status"), failure);
  } finally {
    client.close();
    await creation.catch(() => {});
  }
});

it("diagnoses an error observer failure while still notifying other observers", () => {
  const { client, socket } = connected();
  const diagnostic = vi.spyOn(console, "error").mockImplementation(() => {});
  const failure = new Error("error notice failed"), observer = vi.fn();
  try {
    socket.fakeOpen();
    client.onError(() => { throw failure; });
    client.onError(observer);
    socket.fakeCloseWithCode(1009);
    expect(observer).toHaveBeenCalledWith({ kind: "message_too_big" });
    expect(diagnostic).toHaveBeenCalledWith(expect.stringContaining("error"), failure);
    expect(client.status).toBe("closed");
  } finally { client.close(); }
});

it("a failed initial transcript replay releases ownership and retains the unconsumed tail", () => {
  const { client, socket } = connected();
  try {
    socket.fakeOpen();
    for (const text of ["first", "second", "third"]) {
      socket.fakeMessage({ event: "delta", chat_id: "worker", text });
    }
    const failure = new Error("transcript hydration failed"), attempted: string[] = [];
    expect(() => client.onTranscript("worker", event => {
      if (event.event !== "delta") return;
      attempted.push(event.text);
      if (event.text === "second") throw failure;
    })).toThrow(failure);
    expect(attempted).toEqual(["first", "second"]);
    const retry = vi.fn();
    const unsubscribe = client.onTranscript("worker", retry);
    expect(retry.mock.calls.map(([event]) => event.text)).toEqual(["second", "third"]);
    unsubscribe();
  } finally { client.close(); }
});

it("a chat observer failure does not interrupt another observer or transcript owner", () => {
  const { client, socket } = connected();
  const diagnostic = vi.spyOn(console, "error").mockImplementation(() => {});
  const failure = new Error("side panel failed"), observer = vi.fn(), transcript = vi.fn();
  try {
    socket.fakeOpen();
    client.onChat("worker", () => { throw failure; });
    client.onChat("worker", observer);
    client.onTranscript("worker", transcript);
    const event = { event: "delta", chat_id: "worker", text: "still streaming" };
    expect(() => socket.fakeMessage(event)).not.toThrow();
    expect(observer).toHaveBeenCalledWith(event);
    expect(transcript).toHaveBeenCalledWith(event);
    expect(diagnostic).toHaveBeenCalledWith(expect.stringContaining("chat observer"), failure);
  } finally { client.close(); }
});
