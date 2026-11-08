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
  const hook = renderHook(({ palette }) => useTerminalSession({ client, terminalKey: "tab-key", nodeId: "local", active: true,
    onCloseReady: ready, paletteRevision: palette, exitedText: code => `Exited ${code}` }), { initialProps: { palette: "light" } });
  hook.result.current.host.current = document.createElement("div");
  return { ...hook, close: () => ready.mock.lastCall![0]() };
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
    view.rerender({ palette: "dark" });
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
