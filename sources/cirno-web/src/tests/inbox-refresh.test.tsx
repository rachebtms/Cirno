import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import { InboxProvider, useInbox, type InboxPage } from "@/features/inbox/model/store";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";

vi.mock("@/lib/browser-notifications", () => ({ showBrowserNotification: vi.fn().mockResolvedValue("skipped") }));
vi.mock("@/lib/notification-sound", () => ({ playTurnCompleteSound: vi.fn() }));

const page = (read: boolean): InboxPage => ({
  items: [{ id: "one", seq: 1, category: "system", kind: "compaction", status: "succeeded",
    session_key: "websocket:one", body: "Checkpoint", data: {}, created_at: 1, read_at: read ? 2 : null }],
  unread: { operations: 0, conversations: 0, system: read ? 0 : 1 }, latest_seq: 1, next_before: null,
});

it("does not let an in-flight poll undo a completed mark-read action", async () => {
  let release!: (value: InboxPage) => void;
  let calls = 0;
  const requestMutation = vi.fn(async (_method, payload) => {
    if (payload.action === "inbox.read") return {};
    calls++;
    if (calls === 2) return new Promise<InboxPage>(resolve => { release = resolve; });
    return page(calls > 2);
  });
  const client = { requestMutation, status: "open", onStatus: () => () => {} } as unknown as CirnoClient;
  const { result } = renderHook(useInbox, { wrapper: ({ children }: { children: ReactNode }) =>
    <ClientProvider client={client} token="test"><InboxProvider>{children}</InboxProvider></ClientProvider> });
  await waitFor(() => expect(result.current.snapshot.unread.system).toBe(1));
  let poll!: Promise<void>;
  act(() => { poll = result.current.refresh(); });
  await waitFor(() => expect(release).toBeDefined());
  await act(async () => { await result.current.markRead(["one"]); });
  await act(async () => { release(page(false)); await poll; });
  expect(result.current.snapshot.items[0].read_at).not.toBeNull();
  expect(result.current.snapshot.unread.system).toBe(0);
});

it("ignores responses from a replaced connection", async () => {
  let release!: (value: InboxPage) => void;
  const connection = (requestMutation: unknown) => ({ requestMutation, status: "open", onStatus: () => () => {} }) as unknown as CirnoClient;
  let client = connection(vi.fn(() => new Promise<InboxPage>(resolve => { release = resolve; })));
  const { result, rerender } = renderHook(useInbox, { wrapper: ({ children }: { children: ReactNode }) =>
    <ClientProvider client={client} token="test"><InboxProvider>{children}</InboxProvider></ClientProvider> });
  await waitFor(() => expect(release).toBeDefined());
  client = connection(vi.fn().mockResolvedValue(page(true)));
  rerender();
  await waitFor(() => expect(result.current.snapshot.items).toHaveLength(1));
  await act(async () => { release(page(false)); });
  expect(result.current.snapshot.unread.system).toBe(0);
  expect(result.current.snapshot.items[0].read_at).not.toBeNull();
});
