import { useThreadModels } from "@/components/thread/useThreadModels";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { ClientProvider } from "@/providers/ClientProvider";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { settingsPayload } from "./settings-test-utils";
import { createStreamClient } from "./stream-client";

function pendingResponse() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((finish) => { resolve = finish; });
  return { promise, resolve };
}

function response(settings: SettingsPayload) {
  return new Response(JSON.stringify(settings), { status: 200, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

it("does not overwrite a newer settings snapshot with an older in-flight catalog", async () => {
  const { client } = createStreamClient();
  const pending = pendingResponse();
  vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending.promise));
  const current = settingsPayload();
  current.agent.model = "new-model";
  const { result, rerender } = renderHook(({ snapshot }: { snapshot: SettingsPayload | null }) =>
    useThreadModels({ session: null, settingsSnapshot: snapshot, settingsLoading: false }), {
    initialProps: { snapshot: null as SettingsPayload | null },
    wrapper: ({ children }: { children: ReactNode }) => <ClientProvider client={client} token="fixture">{children}</ClientProvider>,
  });
  rerender({ snapshot: current });
  await act(async () => { pending.resolve(response(settingsPayload())); });
  expect(result.current.settings?.agent.model).toBe("new-model");
});

it("keeps the last successful catalog and exposes a failed refresh", async () => {
  const { client } = createStreamClient();
  let refresh = () => { };
  vi.spyOn(client, "onRuntimeModelUpdate").mockImplementation((callback) => {
    refresh = () => callback(null);
    return () => { };
  });
  const current = settingsPayload();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Provider unavailable", { status: 503 })));
  const { result } = renderHook(() => useThreadModels({
    session: null, settingsSnapshot: current, settingsLoading: false,
  }), { wrapper: ({ children }: { children: ReactNode }) => <ClientProvider client={client} token="fixture">{children}</ClientProvider> });
  await act(async () => { refresh(); });
  expect(result.current.settings).toBe(current);
  expect(result.current.modelSettingsError).toContain("Provider unavailable");
});

it("keeps the newest runtime refresh when responses arrive out of order", async () => {
  const { client } = createStreamClient();
  let refresh = () => { };
  vi.spyOn(client, "onRuntimeModelUpdate").mockImplementation((callback) => {
    refresh = () => callback(null);
    return () => { };
  });
  const first = pendingResponse(), second = pendingResponse();
  vi.stubGlobal("fetch", vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise));
  const current = settingsPayload();
  const { result } = renderHook(() => useThreadModels({
    session: null, settingsSnapshot: current, settingsLoading: false,
  }), { wrapper: ({ children }: { children: ReactNode }) => <ClientProvider client={client} token="fixture">{children}</ClientProvider> });
  act(() => { refresh(); refresh(); });
  const newer = settingsPayload();
  newer.agent.model = "latest-model";
  await act(async () => { second.resolve(response(newer)); });
  await act(async () => { first.resolve(response(current)); });
  expect(result.current.settings?.agent.model).toBe("latest-model");
});
