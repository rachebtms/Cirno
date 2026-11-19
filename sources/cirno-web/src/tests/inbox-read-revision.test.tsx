import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { InboxProvider, useInbox, type InboxPage } from "@/features/inbox/model/store";
import { useInboxFeed } from "@/features/inbox/model/useInboxFeed";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";

vi.mock("@/lib/browser-notifications", () => ({ showBrowserNotification: vi.fn().mockResolvedValue("skipped") }));
vi.mock("@/lib/notification-sound", () => ({ playTurnCompleteSound: vi.fn() }));
afterEach(cleanup);

it.each(["provider-arrival", "provider-update", "feed-arrival", "feed-update"])("does not hide newer unread state behind an old receipt (%s)", async scenario => {
  window.history.replaceState(null, "", "#/inbox?category=system");
  const initial: InboxPage = { revision: 1, items: [{ revision: 1, id: "one", seq: 1, category: "system", kind: "compaction", status: "pending",
    session_key: "websocket:one", body: "before", data: {}, created_at: 1, read_at: null }],
  unread: { operations: 0, conversations: 0, system: 1 }, latest_seq: 1, next_before: null };
  const update = { ...initial.items[0], revision: 3, body: "after", status: "failed" };
  const fresh: InboxPage = { ...initial, revision: 3, items: scenario.endsWith("arrival")
    ? [{ ...update, id: "new", seq: 2 }, { ...initial.items[0], read_at: 2 }]
    : [update], latest_seq: scenario.endsWith("arrival") ? 2 : 1 };
  let resolve!: (value: unknown) => void;
  const receipt = new Promise(done => { resolve = done; });
  let changed = false, refreshFails = false;
  const requestMutation = vi.fn(async (_method, payload) => {
    if (payload.action === "inbox.read") return receipt;
    if (refreshFails) throw new Error("Refresh unavailable");
    return changed ? fresh : initial;
  });
  const client = { requestMutation, status: "open", onStatus: () => () => {} } as unknown as CirnoClient;
  const { result } = renderHook(() => ({ inbox: useInbox(), feed: useInboxFeed(vi.fn()) }), {
    wrapper: ({ children }: { children: ReactNode }) => <ClientProvider client={client} token="fixture"><InboxProvider>{children}</InboxProvider></ClientProvider>,
  });
  await waitFor(() => expect(result.current.feed.page?.items[0]?.body).toBe("before"));
  let marking!: Promise<unknown>;
  act(() => { marking = scenario.startsWith("feed") ? result.current.feed.markAllRead() : result.current.inbox.markRead(); });
  changed = true;
  await act(() => result.current.inbox.refresh());
  expect(result.current.inbox.snapshot.items[0].body).toBe("after");
  refreshFails = true;
  await act(async () => {
    resolve({ ok: true, revision: 2, read_at: 2, unread: { operations: 0, conversations: 0, system: 0 } });
    await marking;
  });
  expect(result.current.inbox.snapshot.unread.system).toBe(1);
  expect(result.current.inbox.snapshot.items[0].read_at).toBeNull();
  expect(result.current.feed.page?.items[0]?.read_at).toBeNull();
});
