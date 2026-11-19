import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CirnoClient } from "@/lib/cirno-client";
import { useTerminalSession } from "@/features/terminal/model/useTerminalSession";

const rendering = vi.hoisted(() => ({ instances: [] as Array<{
  terminal: { cols: number; rows: number; options: { disableStdin: boolean; theme?: unknown };
    onData: (callback: (text: string) => void) => { dispose: () => void };
    onResize: (callback: () => void) => { dispose: () => void };
    write: ReturnType<typeof vi.fn>; writeln: ReturnType<typeof vi.fn>; reset: ReturnType<typeof vi.fn>;
    focus: ReturnType<typeof vi.fn>; dispose: ReturnType<typeof vi.fn> };
  fit: { fit: ReturnType<typeof vi.fn> }; input: (text: string) => void;
}> }));
vi.mock("@/features/terminal/model/renderer", () => ({
  terminalPalette: () => ({ background: "snow" }),
  createTerminalRenderer: () => {
    const instance = { terminal: { cols: 80, rows: 24, options: { disableStdin: true },
      onData: (callback: (text: string) => void) => { instance.input = callback; return { dispose: vi.fn() }; },
      onResize: () => ({ dispose: vi.fn() }), write: vi.fn(), writeln: vi.fn(), reset: vi.fn(), focus: vi.fn(), dispose: vi.fn() },
      fit: { fit: vi.fn() }, input: (text: string) => { void text; } };
    rendering.instances.push(instance); return instance;
  },
}));

interface Output { data: string; cursor: number; reset: boolean; exit_code: number | null }
function pending<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }
function output(data = ""): Output { return { data, cursor: data.length, reset: false, exit_code: null }; }
type Payload = { action: string; values: Record<string, unknown> };
function mount(request: ReturnType<typeof vi.fn>) {
  const client = { requestMutation: request } as unknown as CirnoClient;
  const ready = vi.fn<(close: () => Promise<void>) => void>();
  const props = { client, terminalKey: "tab-key", nodeId: "local", cwd: undefined as string | undefined, ready, palette: "light" };
  const hook = renderHook(({ palette, ready, ...context }) => useTerminalSession({ ...context, active: true,
    onCloseReady: ready, paletteRevision: palette, exitedText: code => `Exited ${code}` }), { initialProps: props });
  hook.result.current.host.current = document.createElement("div");
  return { ...hook, props, close: () => ready.mock.lastCall![0]() };
}
function server(overrides: (payload: Payload) => unknown = () => undefined) {
  return vi.fn((_name: string, payload: Payload) => overrides(payload) ?? (payload.action === "terminal.create"
    ? Promise.resolve({ id: "pty" }) : payload.action === "terminal.read" ? pending<Output>().promise : Promise.resolve({ ok: true })));
}
afterEach(() => { rendering.instances.length = 0; vi.restoreAllMocks(); });

describe("terminal resource ownership", () => {
  it("waits for creation before closing and closes the same resource only once", async () => {
    const opening = pending<{ id: string }>();
    const request = server(payload => payload.action === "terminal.create" ? opening.promise : undefined);
    const view = mount(request);
    await act(async () => view.result.current.connect());
    let closing!: Promise<void>;
    act(() => { closing = view.close(); });
    expect(request.mock.calls.some(([, p]) => p.action === "terminal.close")).toBe(false);
    await act(async () => { opening.resolve({ id: "pty" }); await closing; });
    await act(async () => view.close());
    view.unmount();
    expect(request.mock.calls.filter(([, p]) => p.action === "terminal.close")).toEqual([
      ["workbench.action", { action: "terminal.close", values: { id: "pty" } }],
    ]);
    expect(rendering.instances[0].terminal.dispose).toHaveBeenCalledOnce();
  });

  it("serializes retry cleanup before creating a replacement after an opening failure", async () => {
    const closing = pending<{ ok: boolean }>(); let creates = 0;
    const request = server(payload => {
      if (payload.action === "terminal.create" && ++creates === 1) return Promise.reject(new Error("SSH authentication failed"));
      if (payload.action === "terminal.close") return closing.promise;
    });
    const view = mount(request);
    await act(async () => view.result.current.connect());
    await waitFor(() => expect(view.result.current.phase).toBe("failed"));
    expect(view.result.current.errors).toContain("SSH authentication failed");
    let retry!: Promise<void>;
    act(() => { retry = view.result.current.connect(); });
    expect(creates).toBe(1);
    await act(async () => { closing.resolve({ ok: true }); await retry; });
    await waitFor(() => expect(view.result.current.phase).toBe("connected"));
    expect(creates).toBe(2); expect(view.result.current.errors).toEqual([]);
    expect(rendering.instances[0].terminal.dispose).toHaveBeenCalledOnce();
  });

  it("updates palette without reconnecting, losing output or closing the PTY", async () => {
    const request = server(); const view = mount(request);
    await act(async () => view.result.current.connect());
    await waitFor(() => expect(view.result.current.phase).toBe("connected"));
    view.rerender({ ...view.props, palette: "dark" });
    expect(rendering.instances).toHaveLength(1);
    expect(rendering.instances[0].terminal.options.theme).toEqual({ background: "snow" });
    expect(request.mock.calls.filter(([, p]) => p.action === "terminal.create")).toHaveLength(1);
    expect(request.mock.calls.some(([, p]) => p.action === "terminal.close")).toBe(false);
  });
});

describe("terminal recovery and output", () => {
  it("keeps input failures visible when a concurrent output read succeeds", async () => {
    const reading = pending<Output>();
    const request = server(payload => payload.action === "terminal.read" ? reading.promise
      : payload.action === "terminal.write" ? Promise.reject(new Error("Input was not delivered")) : undefined);
    const view = mount(request);
    await act(async () => view.result.current.connect());
    await waitFor(() => expect(view.result.current.phase).toBe("connected"));
    await act(async () => rendering.instances[0].input("ls\r"));
    expect(view.result.current.errors).toEqual(["Input was not delivered"]);
    await act(async () => reading.resolve(output("server output")));
    expect(rendering.instances[0].terminal.write).toHaveBeenCalledWith("server output");
    expect(view.result.current.errors).toEqual(["Input was not delivered"]);
  });

  it("does not overlap reads when the page wakes while an earlier read is pending", async () => {
    const reading = pending<Output>();
    const request = server(payload => payload.action === "terminal.read" ? reading.promise : undefined);
    const view = mount(request);
    await act(async () => view.result.current.connect());
    await waitFor(() => expect(view.result.current.phase).toBe("connected"));
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(request.mock.calls.filter(([, p]) => p.action === "terminal.read")).toHaveLength(1);
    await act(async () => reading.resolve(output("one chunk")));
    expect(rendering.instances[0].terminal.write).toHaveBeenCalledExactlyOnceWith("one chunk");
  });

  it("restores a retained terminal after close fails and ignores output arriving after a successful close", async () => {
    const reading = pending<Output>(); let closes = 0;
    const request = server(payload => {
      if (payload.action === "terminal.close" && ++closes === 1) return Promise.reject(new Error("Close request failed"));
      if (payload.action === "terminal.read") return reading.promise;
    });
    const view = mount(request);
    await act(async () => view.result.current.connect());
    await waitFor(() => expect(view.result.current.phase).toBe("connected"));
    await act(async () => { await expect(view.close()).rejects.toThrow("Close request failed"); });
    expect(view.result.current.phase).toBe("connected");
    expect(rendering.instances[0].terminal.options.disableStdin).toBe(false);
    expect(view.result.current.errors).toEqual(["Close request failed"]);
    await act(async () => { await view.close(); reading.resolve(output("late output")); });
    expect(rendering.instances[0].terminal.write).not.toHaveBeenCalled();
    expect(view.result.current.errors).toEqual([]);
    expect(closes).toBe(2);
  });
});


describe("terminal context transitions", () => {
  for (const field of ["client", "nodeId"] as const) {
    it(`requires a new explicit connection after ${field} changes`, async () => {
      const request = server(), next = server();
      const view = mount(request);
      await act(async () => view.result.current.connect());
      await waitFor(() => expect(view.result.current.phase).toBe("connected"));
      const retiredConnect = view.result.current.connect;
      view.rerender({ ...view.props, ...(field === "client" ? { client: { requestMutation: next } as unknown as CirnoClient } : { nodeId: "remote" }) });
      await act(async () => {});
      expect(view.result.current.phase).toBe("idle");
      expect(view.result.current.started).toBe(false);
      await act(async () => retiredConnect());
      expect(next.mock.calls.filter(([, p]) => p.action === "terminal.create")).toHaveLength(0);
      expect(request.mock.calls.filter(([, p]) => p.action === "terminal.create")).toHaveLength(1);
      await act(async () => view.result.current.connect());
      await waitFor(() => expect(view.result.current.phase).toBe("connected"));
      const target = field === "client" ? next : request;
      expect(target.mock.lastCall?.[1].action).not.toBe("terminal.close");
      expect(target.mock.calls.filter(([, p]) => p.action === "terminal.create")).toHaveLength(field === "client" ? 1 : 2);
    });
  }
  it("updates close registration without recreating its terminal", async () => {
    const request = server(), view = mount(request);
    await act(async () => view.result.current.connect());
    await waitFor(() => expect(view.result.current.phase).toBe("connected"));
    const nextReady = vi.fn<(close: () => Promise<void>) => void>();
    view.rerender({ ...view.props, ready: nextReady });
    await act(async () => {});
    expect(request.mock.calls.filter(([, p]) => p.action === "terminal.create")).toHaveLength(1);
    expect(request.mock.calls.filter(([, p]) => p.action === "terminal.close")).toHaveLength(0);
    expect(nextReady).toHaveBeenCalled();
    await act(async () => nextReady.mock.lastCall![0]());
    expect(request.mock.calls.filter(([, p]) => p.action === "terminal.close")).toHaveLength(1);
  });
  it("does not finish a retired retry by starting a terminal in the replacement context", async () => {
    const closing = pending<{ ok: boolean }>();
    const request = server(p => p.action === "terminal.create" ? Promise.reject(new Error("Opening failed"))
      : p.action === "terminal.close" ? closing.promise : undefined);
    const next = server(), view = mount(request);
    await act(async () => view.result.current.connect());
    await waitFor(() => expect(view.result.current.phase).toBe("failed"));
    let retry!: Promise<void>;
    act(() => { retry = view.result.current.connect(); });
    view.rerender({ ...view.props, client: { requestMutation: next } as unknown as CirnoClient });
    await act(async () => { closing.resolve({ ok: true }); await retry; });
    expect(next.mock.calls.some(([, p]) => p.action === "terminal.create")).toBe(false);
    expect(view.result.current.phase).toBe("idle");
    expect(view.result.current.errors).toEqual([]);
  });
  it("does not let a retired input error overwrite the replacement context", async () => {
    let reject!: (error: Error) => void;
    const writing = new Promise<never>((_resolve, fail) => { reject = fail; });
    const request = server(p => p.action === "terminal.write" ? writing : undefined);
    const view = mount(request);
    await act(async () => view.result.current.connect());
    await waitFor(() => expect(view.result.current.phase).toBe("connected"));
    act(() => rendering.instances[0].input("old input"));
    await act(async () => {});
    view.rerender({ ...view.props, nodeId: "remote" });
    await act(async () => { reject(new Error("Old input failed")); });
    expect(view.result.current.errors).toEqual([]);
    expect(view.result.current.phase).toBe("idle");
  });
  it("does not restart reads or repeat the exit banner when the page wakes", async () => {
    const reading = pending<Output>();
    const request = server(p => p.action === "terminal.read" ? reading.promise : undefined);
    const view = mount(request);
    await act(async () => view.result.current.connect());
    await act(async () => reading.resolve({ ...output("final"), exit_code: 0 }));
    expect(view.result.current.phase).toBe("exited");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    await act(async () => {});
    expect(request.mock.calls.filter(([, p]) => p.action === "terminal.read")).toHaveLength(1);
    expect(rendering.instances[0].terminal.writeln).toHaveBeenCalledTimes(1);
  });
  it("drains input accepted before a close instead of silently dropping its queued writes", async () => {
    const first = pending<{ ok: boolean }>();
    const request = server(p => p.action === "terminal.write" && p.values.data === "first" ? first.promise : undefined);
    const view = mount(request);
    await act(async () => view.result.current.connect());
    act(() => rendering.instances[0].input("first"));
    await act(async () => {});
    let closing!: Promise<void>;
    act(() => { rendering.instances[0].input("second"); closing = view.close(); });
    await act(async () => { first.resolve({ ok: true }); await closing; });
    expect(request.mock.calls.filter(([, p]) => p.action === "terminal.write").map(([, p]) => p.values.data)).toEqual(["first", "second"]);
    const operations = request.mock.calls.map(([, p]) => p.action);
    expect(operations.lastIndexOf("terminal.write")).toBeLessThan(operations.indexOf("terminal.close"));
  });
});

it("waits for the old context close before an explicit replacement connection", async () => {
  const closing = pending<{ ok: boolean }>();
  const request = server(p => p.action === "terminal.close" ? closing.promise : undefined);
  const next = server(), view = mount(request);
  await act(async () => view.result.current.connect());
  await waitFor(() => expect(view.result.current.phase).toBe("connected"));
  view.rerender({ ...view.props, client: { requestMutation: next } as unknown as CirnoClient });
  let connecting!: Promise<void>;
  act(() => { connecting = view.result.current.connect(); });
  expect(next.mock.calls.some(([, p]) => p.action === "terminal.create")).toBe(false);
  await act(async () => { closing.resolve({ ok: true }); await connecting; });
  expect(view.result.current.phase).toBe("connected");
  expect(next.mock.calls.filter(([, p]) => p.action === "terminal.create")).toHaveLength(1);
  expect(request.mock.calls.filter(([, p]) => p.action === "terminal.close")).toHaveLength(1);
});
it("keeps an exited terminal disabled after a close failure and allows reconnect", async () => {
  const request = server(p => p.action === "terminal.read" ? Promise.resolve({ ...output(), exit_code: 0 }) : undefined);
  let closes = 0;
  request.mockImplementation((_name: string, p: Payload) => p.action === "terminal.close" && ++closes === 1
    ? Promise.reject(new Error("Close failed")) : p.action === "terminal.create" ? Promise.resolve({ id: "pty" })
      : p.action === "terminal.read" ? Promise.resolve({ ...output(), exit_code: 0 }) : Promise.resolve({ ok: true }));
  const view = mount(request);
  await act(async () => view.result.current.connect());
  await waitFor(() => expect(view.result.current.phase).toBe("exited"));
  await act(async () => { await expect(view.close()).rejects.toThrow("Close failed"); });
  expect(view.result.current.phase).toBe("exited");
  expect(rendering.instances[0].terminal.options.disableStdin).toBe(true);
  expect(request.mock.calls.filter(([, p]) => p.action === "terminal.read")).toHaveLength(1);
  await act(async () => view.result.current.connect());
  expect(request.mock.calls.filter(([, p]) => p.action === "terminal.create")).toHaveLength(2);
});
