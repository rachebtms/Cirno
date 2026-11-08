import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CirnoClient } from "@/lib/cirno-client";
import { useTrace } from "@/features/trace/useTrace";
import type { RecordingInfo, TraceDetail, TraceEvent, TracePage } from "@/features/trace/contracts";

const event: TraceEvent = { id: 1, kind: "input", session_key: "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", summary: "first", created_ms: 1000, status: "", turn_id: "turn" };
const info = (epoch = "a"): RecordingInfo => ({ id: "recording", epoch, running: true, reason: null, count: 1, created_ms: 1000 });
const page = (epoch = "a"): TracePage => ({ ...info(epoch), events: [event], before: null, sources: [event.session_key] });
function pending<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((done) => { resolve = done; }); return { promise, resolve }; }

describe("diagnostic recording ownership", () => {
  it("clear ignores late details and old pages and sends both filters to the server", async () => {
    const lateDetail = pending<TraceDetail>();
    const latePage = pending<TracePage>();
    let hold = false, epoch = "a";
    const request = vi.fn((_name: string, payload: { action: string }) => {
      if (payload.action === "trace.detail") return lateDetail.promise;
      if (payload.action === "trace.clear") { epoch = "b"; return Promise.resolve(info(epoch)); }
      if (payload.action === "trace.create") return Promise.resolve(info(epoch));
      return hold && epoch === "a" ? latePage.promise : Promise.resolve(page(epoch));
    });
    const client = { requestMutation: request } as unknown as CirnoClient;
    const ready = vi.fn();
    const { result } = renderHook(() => useTrace(client, "recording", true, ready));
    await waitFor(() => expect(result.current.page?.epoch).toBe("a"));
    act(() => result.current.setSelected(event));
    await waitFor(() => expect(result.current.detailBusy).toBe(true));
    hold = true;
    act(() => result.current.refresh());
    await act(async () => result.current.control("clear"));
    await waitFor(() => expect(result.current.page?.epoch).toBe("b"));
    await act(async () => { lateDetail.resolve({ event: "old body" }); latePage.resolve(page("a")); });
    expect(result.current.detail).toBeNull(); expect(result.current.selected).toBeNull();
    expect(result.current.page?.epoch).toBe("b");
    act(() => { result.current.setSource("websocket:worker"); result.current.setKind("tool"); });
    await waitFor(() => expect(request).toHaveBeenCalledWith("workbench.action", expect.objectContaining({ action: "trace.events", values: expect.objectContaining({ kind: "tool", session_key: "websocket:worker" }) })));
  });

  it("waits for create before closing a tab, then explicitly deletes its recording", async () => {
    const opening = pending<RecordingInfo>();
    const request = vi.fn((_name: string, payload: { action: string }) => payload.action === "trace.create" ? opening.promise : Promise.resolve({ ok: true }));
    const client = { requestMutation: request } as unknown as CirnoClient;
    let close!: () => Promise<void>;
    const ready = (callback: () => Promise<void>) => { close = callback; };
    renderHook(() => useTrace(client, "recording", true, ready));
    let closing!: Promise<void>;
    act(() => { closing = close(); });
    expect(request.mock.calls.some(([, payload]) => payload.action === "trace.close")).toBe(false);
    await act(async () => { opening.resolve(info()); await closing; });
    expect(request).toHaveBeenCalledWith("workbench.action", { action: "trace.close", values: { recording_id: "recording" } });
  });
});

describe("recording server restart recovery", () => {
  it("refresh recreates an expired recording and closes the old inspector", async () => {
    let epoch = "before-restart";
    const request = vi.fn((_name: string, payload: { action: string }) => Promise.resolve(
      payload.action === "trace.create" ? info(epoch) : payload.action === "trace.detail" ? { event: "old body" } : page(epoch)
    ));
    const client = { requestMutation: request } as unknown as CirnoClient;
    const ready = vi.fn();
    const { result } = renderHook(() => useTrace(client, "recording", true, ready));
    await waitFor(() => expect(result.current.page?.epoch).toBe("before-restart"));
    act(() => result.current.setSelected(event));
    await waitFor(() => expect(result.current.detail?.event).toBe("old body"));
    epoch = "after-restart";
    act(() => result.current.refresh());
    await waitFor(() => expect(result.current.page?.epoch).toBe("after-restart"));
    expect(result.current.selected).toBeNull(); expect(result.current.detail).toBeNull();
    expect(request.mock.calls.filter(([, payload]) => payload.action === "trace.create")).toHaveLength(2);
  });
});

it("shows a non-Error recording failure and permits an explicit retry", async () => {
  const request = vi.fn().mockRejectedValueOnce("Recording service unavailable")
    .mockImplementation((_name: string, payload: { action: string }) => Promise.resolve(payload.action === "trace.create" ? info() : page()));
  const ready = vi.fn();
  const client = { requestMutation: request } as unknown as CirnoClient;
  const { result } = renderHook(() => useTrace(client, "recording", true, ready));
  await waitFor(() => expect(result.current.error).toBe("Recording service unavailable"));
  act(() => result.current.refresh());
  await waitFor(() => expect(result.current.page?.events).toHaveLength(1));
  expect(result.current.error).toBe("");
});
