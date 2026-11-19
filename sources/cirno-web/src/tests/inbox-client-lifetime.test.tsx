import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { useLayoutEffect, type ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { InboxProvider, useInbox, type InboxPage } from "@/features/inbox/model/store";
import { useInboxFeed } from "@/features/inbox/model/useInboxFeed";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";
import { SurfaceVisibilityContext } from "@/hooks/usePageVisibility";

vi.mock("@/lib/browser-notifications", () => ({ showBrowserNotification: vi.fn().mockResolvedValue("skipped") }));
vi.mock("@/lib/notification-sound", () => ({ playTurnCompleteSound: vi.fn() }));

function pending<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function page(owner: string): InboxPage {
  return { items: [{ id: "shared-id", seq: 1, category: "system", kind: "approval", status: "pending",
    session_key: "websocket:fixture", body: owner, data: { approval_id: "fixture" }, created_at: 1, read_at: null }],
  unread: { operations: 0, conversations: 0, system: 1 }, latest_seq: 1, next_before: null };
}
const receipt = { ok: true, read_at: 2, unread: { operations: 0, conversations: 0, system: 0 } };
function connection(owner: string, override?: (action: string, values?: Record<string, unknown>) => unknown) {
  const request = vi.fn(async (_method, payload) => override?.(payload.action, payload.values) ?? page(owner));
  return { request, client: { requestMutation: request, status: "open", onStatus: () => () => {} } as unknown as CirnoClient };
}
function mount<T>(initial: CirnoClient, hook: () => T) {
  let client = initial;
  let visible = true;
  const rendered = renderHook(hook, { wrapper: ({ children }: { children: ReactNode }) =>
    <ClientProvider client={client} token="fixture"><InboxProvider><SurfaceVisibilityContext.Provider value={visible}>{children}</SurfaceVisibilityContext.Provider></InboxProvider></ClientProvider> });
  return { ...rendered, replace(next: CirnoClient) { client = next; rendered.rerender(); }, visible(value: boolean) { visible = value; rendered.rerender(); } };
}
beforeEach(() => { window.history.replaceState(null, "", "#/inbox?category=system"); });
afterEach(cleanup);

it("retains an initial category read across hiding and showing the same Inbox", async () => {
  const category = pending<InboxPage>();
  const first = connection("first", (action, values) => action === "inbox.list" && values?.category ? category.promise : undefined);
  const view = mount(first.client, () => useInboxFeed(vi.fn()));
  await waitFor(() => expect(first.request.mock.calls.some(([, payload]) => payload.values?.category === "system")).toBe(true));
  view.visible(false);
  view.visible(true);
  await act(async () => { category.resolve(page("first")); });
  expect(view.result.current.page?.items[0]?.body).toBe("first");
});

it("hides a previous Inbox snapshot before layout effects observe the replacement", async () => {
  const first = connection("first"), second = connection("second");
  let current = first.client;
  const observed = vi.fn();
  const view = mount(first.client, () => {
    const inbox = useInbox();
    useLayoutEffect(() => { observed(current, inbox.snapshot.items); }, [current]);
    return inbox;
  });
  await waitFor(() => expect(view.result.current.snapshot.items[0]?.body).toBe("first"));
  current = second.client;
  view.replace(second.client);
  expect(observed).toHaveBeenLastCalledWith(second.client, []);
});

it("rejects a retired mark-read receipt after connection A-B-A", async () => {
  const read = pending<typeof receipt>();
  let rejectReads = false;
  const first = connection("first", action => {
    if (action === "inbox.read") return read.promise;
    if (rejectReads) throw new Error("Retired refresh must not run");
  });
  const second = connection("second");
  const view = mount(first.client, useInbox);
  await waitFor(() => expect(view.result.current.snapshot.items[0]?.body).toBe("first"));
  let marking!: ReturnType<ReturnType<typeof useInbox>["markRead"]>;
  act(() => { marking = view.result.current.markRead(); });
  view.replace(second.client);
  await waitFor(() => expect(view.result.current.snapshot.items[0]?.body).toBe("second"));
  view.replace(first.client);
  await waitFor(() => expect(view.result.current.snapshot.items[0]?.body).toBe("first"));
  rejectReads = true;
  const calls = first.request.mock.calls.length;
  await act(async () => { read.resolve(receipt); await marking; });
  expect(view.result.current.snapshot.items[0].read_at).toBeNull();
  expect(view.result.current.snapshot.unread.system).toBe(1);
  expect(view.result.current.error).toBeNull();
  expect(first.request).toHaveBeenCalledTimes(calls);
});

it("does not run a refresh callback retained from a replaced Inbox", async () => {
  const first = connection("first"), second = connection("second");
  const view = mount(first.client, useInbox);
  await waitFor(() => expect(view.result.current.snapshot.items[0]?.body).toBe("first"));
  const retired = view.result.current.refresh;
  view.replace(second.client);
  await waitFor(() => expect(view.result.current.snapshot.items[0]?.body).toBe("second"));
  const calls = first.request.mock.calls.length;
  await act(() => retired());
  expect(first.request).toHaveBeenCalledTimes(calls);
  expect(view.result.current.snapshot.items[0]?.body).toBe("second");
});

it("does not apply an old view's mark-all receipt to replacement rows with matching IDs", async () => {
  const read = pending<typeof receipt>();
  const first = connection("first", action => action === "inbox.read" ? read.promise : undefined);
  const second = connection("second");
  const view = mount(first.client, () => useInboxFeed(vi.fn()));
  await waitFor(() => expect(view.result.current.page?.items[0]?.body).toBe("first"));
  let marking!: Promise<void>;
  act(() => { marking = view.result.current.markAllRead(); });
  view.replace(second.client);
  await waitFor(() => expect(view.result.current.page?.items[0]?.body).toBe("second"));
  await act(async () => { read.resolve(receipt); await marking; });
  expect(view.result.current.page?.items[0]?.read_at).toBeNull();
  expect(view.result.current.unread.system).toBe(1);
});

it("keeps replacement approval work independent of an old connection's pending action", async () => {
  const old = pending<unknown>(), next = pending<unknown>();
  const first = connection("first", action => action === "approvals.decide" ? old.promise : undefined);
  const second = connection("second", action => action === "approvals.decide" ? next.promise : undefined);
  const view = mount(first.client, () => useInboxFeed(vi.fn()));
  await waitFor(() => expect(view.result.current.page?.items[0]?.body).toBe("first"));
  let deciding!: Promise<void>, replacing!: Promise<void>;
  act(() => { deciding = view.result.current.decide(view.result.current.page!.items[0], true); });
  view.replace(second.client);
  await waitFor(() => expect(view.result.current.page?.items[0]?.body).toBe("second"));
  act(() => { replacing = view.result.current.decide(view.result.current.page!.items[0], false); });
  const submitted = second.request.mock.calls.filter(([, payload]) => payload.action === "approvals.decide").length;
  try {
    await act(async () => { old.resolve({ ok: true }); await deciding; });
    expect(submitted).toBe(1);
    expect(view.result.current.busy).toBe("shared-id");
  } finally {
    await act(async () => { old.resolve({ ok: true }); next.resolve({ ok: true }); await Promise.all([deciding, replacing]); });
  }
});
