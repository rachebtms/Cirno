import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useSessions } from "@/hooks/useSessions";
import * as api from "@/lib/api";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { CirnoClient } from "@/lib/cirno-client";
import { ClientProvider } from "@/providers/ClientProvider";
import { webuiThreadCache } from "@/lib/webui-thread-cache";

vi.mock("@/lib/api", async importOriginal => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  listSessions: vi.fn(), deleteSession: vi.fn(), fetchSessionAutomations: vi.fn(),
}));
function pending<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }
function fake() { return { onSessionUpdate: () => () => {}, newChat: vi.fn().mockResolvedValue("new"), forkChat: vi.fn().mockResolvedValue("fork") }; }
function row(title: string): ChatSummary { return { key: "websocket:shared", chatId: "shared", channel: "websocket", preview: title, createdAt: null, updatedAt: null, title }; }
function setup(client = fake()) {
  let context = { client, token: "old" };
  const hook = renderHook(() => useSessions(), { wrapper: ({ children }) => <ClientProvider client={context.client as unknown as CirnoClient} token={context.token}>{children}</ClientProvider> });
  return { ...hook, client, change: (client = fake(), token = "next") => { context = { client, token }; hook.rerender(); } };
}
beforeEach(() => {
  vi.mocked(api.listSessions).mockReset().mockImplementation(async token => [row(token)]);
  vi.mocked(api.deleteSession).mockReset().mockResolvedValue({ deleted: true });
  vi.mocked(api.fetchSessionAutomations).mockReset().mockResolvedValue({ jobs: [] });
});
it("revalidates a replacement connection and rejects the delayed old catalog", async () => {
  const old = pending<ChatSummary[]>();
  vi.mocked(api.listSessions).mockImplementation(async token => token === "old" ? old.promise : [row(token)]);
  const view = setup();
  try {
    view.change();
    await act(async () => {});
    expect(api.listSessions).toHaveBeenCalledWith("next");
    await act(async () => old.resolve([row("old")]));
    expect(view.result.current.sessions.map(value => value.title)).toEqual(["next"]);
  } finally { old.resolve([]); }
});
it("does not admit a late created conversation into a replacement connection", async () => {
  const created = pending<string>(), client = fake();
  client.newChat.mockImplementation(() => created.promise);
  const view = setup(client);
  await act(async () => {});
  let result!: Promise<unknown>;
  act(() => { result = view.result.current.createChat().then(value => value, error => error); });
  view.change();
  await act(async () => { created.resolve("from-old-server"); await result; });
  expect(await result).toBeInstanceOf(Error);
  expect(view.result.current.sessions.map(value => value.title)).toEqual(["next"]);
});
it("does not clear current sessions or thread cache after an old deletion settles", async () => {
  const receipt = pending<{ deleted: boolean }>();
  vi.mocked(api.deleteSession).mockImplementation(() => receipt.promise);
  const removeCache = vi.spyOn(webuiThreadCache, "delete");
  const view = setup();
  await act(async () => {});
  let result!: Promise<unknown>;
  act(() => { result = view.result.current.deleteChat("websocket:shared").then(value => value, error => error); });
  view.change();
  await act(async () => { receipt.resolve({ deleted: true }); await result; });
  expect(await result).toBeInstanceOf(Error);
  expect(view.result.current.sessions.map(value => value.title)).toEqual(["next"]);
  expect(removeCache).not.toHaveBeenCalled();
});
for (const action of ["createChat", "forkChat", "deleteChat", "getSessionAutomations"] as const) {
  it(`rejects retained ${action} callbacks before they contact either server`, async () => {
    const view = setup();
    await act(async () => {});
    const retired = view.result.current;
    view.change();
    await act(async () => {});
    await act(async () => {
      const result = action === "createChat" ? retired.createChat() : action === "forkChat" ? retired.forkChat("shared", 0) : retired[action]("websocket:shared");
      await expect(result).rejects.toThrow(/connection|context/i);
    });
    expect(view.client.newChat).not.toHaveBeenCalled();
    expect(view.client.forkChat).not.toHaveBeenCalled();
    expect(api.deleteSession).not.toHaveBeenCalled();
    expect(api.fetchSessionAutomations).not.toHaveBeenCalled();
  });
}
it("keeps the catalog on token renewal and uses the current token on revalidation", async () => {
  const view = setup();
  await act(async () => {});
  view.change(view.client, "renewed");
  expect(view.result.current.sessions.map(value => value.title)).toEqual(["old"]);
  expect(api.listSessions).toHaveBeenCalledTimes(1);
  await act(async () => view.result.current.refresh());
  expect(api.listSessions).toHaveBeenLastCalledWith("renewed");
  expect(view.result.current.sessions.map(value => value.title)).toEqual(["renewed"]);
});
it("does not restore a confirmed deletion from a catalog read begun before it", async () => {
  const stale = pending<ChatSummary[]>();
  vi.mocked(api.listSessions).mockResolvedValueOnce([row("old")]).mockImplementationOnce(() => stale.promise).mockResolvedValue([]);
  const view = setup();
  await act(async () => {});
  let reading!: Promise<void>;
  act(() => { reading = view.result.current.refresh(); });
  await act(async () => view.result.current.deleteChat("websocket:shared"));
  expect(view.result.current.sessions).toEqual([]);
  await act(async () => { stale.resolve([row("old")]); await reading; });
  expect(view.result.current.sessions).toEqual([]);
});
