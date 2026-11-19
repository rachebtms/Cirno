import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { useInboxFeed } from "@/features/inbox/model/useInboxFeed";
import type { InboxNotice, InboxPage } from "@/features/inbox/model/store";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";

const inbox = vi.hoisted(() => ({
  load: vi.fn(), refresh: vi.fn(), markRead: vi.fn(), connected: true, error: null,
  snapshot: { items: [], unread: { operations: 0, conversations: 0, system: 0 }, latest_seq: 0, next_before: null },
}));
vi.mock("@/features/inbox/model/store", async (original) => ({
  ...await original<typeof import("@/features/inbox/model/store")>(), useInbox: () => inbox,
}));
const notice = (id: string, category: "system" | "operations" = "system"): InboxNotice => ({
  id, seq: 5, category, kind: "approval", status: "pending", session_key: "websocket:fixture",
  body: id, data: { approval_id: "approval" }, created_at: 1, read_at: null,
});
const page = (id: string, category: "system" | "operations" = "system"): InboxPage => ({
  items: [notice(id, category)], unread: { operations: 0, conversations: 0, system: 1 }, latest_seq: 5, next_before: 5,
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
function renderFeed(requestMutation = vi.fn()) {
  const client = { requestMutation } as unknown as CirnoClient;
  return renderHook(() => useInboxFeed(vi.fn()), { wrapper: ({ children }: { children: ReactNode }) =>
    <ClientProvider client={client} token="fixture">{children}</ClientProvider> });
}

describe("Inbox feed request ownership", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "#/inbox?category=system");
    inbox.load.mockReset().mockResolvedValue(page("current"));
    inbox.refresh.mockReset().mockResolvedValue(undefined);
    inbox.markRead.mockReset().mockResolvedValue(undefined);
    inbox.connected = true;
  });

  it.each([false, true])("rejects an old pagination result after category A-B-A (error=%s)", async (fails) => {
    const pending = deferred<InboxPage>();
    inbox.load.mockImplementation((category, before) => before ? pending.promise : Promise.resolve(page(`current-${category}`, category)));
    const { result } = renderFeed();
    await waitFor(() => expect(result.current.page?.items[0].id).toBe("current-system"));
    let request!: Promise<void>;
    act(() => { request = result.current.more(); });
    act(() => result.current.selectCategory("operations"));
    await waitFor(() => expect(result.current.page?.items[0].id).toBe("current-operations"));
    act(() => result.current.selectCategory("system"));
    await waitFor(() => expect(result.current.page?.items[0].id).toBe("current-system"));
    await act(async () => {
      if (fails) pending.reject(new Error("Old page failed")); else pending.resolve(page("old-page"));
      await request;
    });
    expect(result.current.page?.items.map(item => item.id)).toEqual(["current-system"]);
    expect(result.current.error).toBeNull();
  });

  it("does not submit a second conflicting approval decision in the same frame", async () => {
    const pending = deferred<unknown>();
    const requestMutation = vi.fn(() => pending.promise);
    const { result } = renderFeed(requestMutation);
    await waitFor(() => expect(result.current.page).not.toBeNull());
    let requests!: Promise<void>[];
    act(() => { requests = [result.current.decide(notice("action"), true), result.current.decide(notice("action"), false)]; });
    const count = requestMutation.mock.calls.length;
    await act(async () => { pending.resolve({}); await Promise.all(requests); });
    expect(count).toBe(1);
    expect(result.current.busy).toBeNull();
  });

  it("discards a pagination response from before disconnect and reconnect", async () => {
    const pending = deferred<InboxPage>();
    inbox.load.mockImplementation((_category, before) => before ? pending.promise : Promise.resolve(page("current")));
    const { result, rerender } = renderFeed();
    await waitFor(() => expect(result.current.page).not.toBeNull());
    let request!: Promise<void>;
    act(() => { request = result.current.more(); });
    act(() => { inbox.connected = false; rerender(); });
    act(() => { inbox.connected = true; rerender(); });
    await waitFor(() => expect(result.current.page?.items[0].id).toBe("current"));
    await act(async () => { pending.resolve(page("before-reconnect")); await request; });
    expect(result.current.page?.items.map(item => item.id)).toEqual(["current"]);
  });
});

it.each(["hidden", "unmounted", "hidden-while-marking"])("ignores late inbox navigation after the view is %s", async mode => {
  const { SurfaceVisibilityContext } = await import("@/hooks/usePageVisibility");
  window.history.replaceState(null, "", "#/inbox?category=system");
  const pending = deferred<{ session_key: string }>();
  const marking = deferred<void>();
  inbox.load.mockReset().mockResolvedValue(page("current"));
  inbox.connected = true;
  inbox.markRead.mockReset().mockImplementation(() => mode === "hidden-while-marking" ? marking.promise : Promise.resolve());
  const select = vi.fn();
  const client = { requestMutation: vi.fn(() => pending.promise) } as unknown as CirnoClient;
  let visible = true;
  const { result, rerender, unmount } = renderHook(() => useInboxFeed(select), { wrapper: ({ children }: { children: ReactNode }) =>
    <ClientProvider client={client} token="fixture"><SurfaceVisibilityContext.Provider value={visible}>{children}</SurfaceVisibilityContext.Provider></ClientProvider> });
  await waitFor(() => expect(result.current.page).not.toBeNull());
  let request!: Promise<void>;
  act(() => { request = result.current.open(notice("current")); });
  if (mode === "hidden-while-marking") {
    await act(async () => { pending.resolve({ session_key: "websocket:fixture" }); });
    await waitFor(() => expect(inbox.markRead).toHaveBeenCalledTimes(1));
  }
  if (mode === "unmounted") unmount();
  else {
    act(() => { visible = false; rerender(); });
    act(() => { visible = true; rerender(); });
  }
  await act(async () => {
    pending.resolve({ session_key: "websocket:fixture" });
    marking.resolve();
    await request;
  });
  expect(select).not.toHaveBeenCalled();
  if (mode !== "hidden-while-marking") expect(inbox.markRead).not.toHaveBeenCalled();
});
