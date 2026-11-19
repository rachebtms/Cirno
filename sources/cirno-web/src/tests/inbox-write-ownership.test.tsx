import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import { InboxProvider, useInbox, type InboxPage } from "@/features/inbox/model/store";
import { useInboxFeed } from "@/features/inbox/model/useInboxFeed";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";

vi.mock("@/lib/browser-notifications", () => ({ showBrowserNotification: vi.fn().mockResolvedValue("skipped") }));
vi.mock("@/lib/notification-sound", () => ({ playTurnCompleteSound: vi.fn() }));
const page = (read: boolean): InboxPage => ({
  items: [{ id: "one", seq: 1, category: "system", kind: "compaction", status: "succeeded",
    session_key: "websocket:one", body: "Checkpoint", data: {}, created_at: 1, read_at: read ? 2 : null }],
  unread: { operations: 0, conversations: 0, system: read ? 0 : 1 }, latest_seq: 1, next_before: null,
});
function wrapper(requestMutation: ReturnType<typeof vi.fn>) {
  const client = { requestMutation, status: "open", onStatus: () => () => {} } as unknown as CirnoClient;
  return ({ children }: { children: ReactNode }) => <ClientProvider client={client} token="fixture"><InboxProvider>{children}</InboxProvider></ClientProvider>;
}

it("retains committed unread counts when the post-write refresh fails", async () => {
  let committed = false;
  const requestMutation = vi.fn(async (_method, payload) => {
    if (payload.action === "inbox.read") {
      committed = true;
      return { ok: true, read_at: 2, unread: page(true).unread };
    }
    if (committed) throw new Error("Refresh unavailable");
    return page(false);
  });
  const { result } = renderHook(useInbox, { wrapper: wrapper(requestMutation) });
  await waitFor(() => expect(result.current.snapshot.unread.system).toBe(1));
  await act(async () => { await result.current.markRead(["one"]); });
  expect(result.current.snapshot.items[0].read_at).not.toBeNull();
  expect(result.current.snapshot.unread.system).toBe(0);
  expect(result.current.error).toBe("Refresh unavailable");
});

it("reissues a category load that spans a completed read write", async () => {
  window.history.replaceState(null, "", "#/inbox?category=system");
  let committed = false;
  let release!: (value: InboxPage) => void;
  let categoryLoads = 0;
  const requestMutation = vi.fn(async (_method, payload) => {
    if (payload.action === "inbox.read") {
      committed = true;
      return { ok: true, read_at: 2, unread: page(true).unread };
    }
    if (payload.values?.category === "system") {
      categoryLoads++;
      if (categoryLoads === 1) return new Promise<InboxPage>(resolve => { release = resolve; });
    }
    return page(committed);
  });
  const { result } = renderHook(() => useInboxFeed(vi.fn()), { wrapper: wrapper(requestMutation) });
  await waitFor(() => expect(release).toBeDefined());
  await act(async () => { await result.current.markAllRead(); });
  await act(async () => { release(page(false)); });
  await waitFor(() => expect(result.current.page?.items[0].read_at).toBe(2));
  expect(categoryLoads).toBe(2);
  expect(result.current.unread.system).toBe(0);
});

it("recovers a failed initial read that predates a committed write", async () => {
  let committed = false;
  let reject!: (reason: Error) => void;
  let reads = 0;
  const requestMutation = vi.fn(async (_method, payload) => {
    if (payload.action === "inbox.read") {
      committed = true;
      return { ok: true, read_at: 2, unread: page(true).unread };
    }
    if (payload.values?.category === "system" && ++reads === 1) {
      return new Promise<InboxPage>((_resolve, fail) => { reject = fail; });
    }
    return page(committed);
  });
  window.history.replaceState(null, "", "#/inbox?category=system");
  const { result } = renderHook(() => useInboxFeed(vi.fn()), { wrapper: wrapper(requestMutation) });
  await waitFor(() => expect(reject).toBeDefined());
  await act(async () => { await result.current.markAllRead(); });
  await act(async () => { reject(new Error("Stale read failed")); });
  await waitFor(() => expect(result.current.page?.items[0].read_at).toBe(2));
  expect(result.current.error).toBeNull();
  expect(reads).toBe(2);
});

it("keeps rows and counts unread and reports a rejected write", async () => {
  window.history.replaceState(null, "", "#/inbox?category=system");
  const requestMutation = vi.fn(async (_method, payload) => {
    if (payload.action === "inbox.read") throw new Error("Write rejected");
    return page(false);
  });
  const { result } = renderHook(() => useInboxFeed(vi.fn()), { wrapper: wrapper(requestMutation) });
  await waitFor(() => expect(result.current.page?.items).toHaveLength(1));
  await act(async () => { await result.current.markAllRead(); });
  expect(result.current.page?.items[0].read_at).toBeNull();
  expect(result.current.unread.system).toBe(1);
  expect(result.current.error).toContain("Write rejected");
  expect(requestMutation.mock.calls.filter(([, payload]) => payload.action === "inbox.list")).toHaveLength(2);
});
