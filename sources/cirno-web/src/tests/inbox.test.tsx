import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { InboxProvider, type InboxNotice } from "@/hooks/useInbox";
import { InboxView } from "@/components/InboxView";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";
import { setAppLanguage } from "@/i18n";
import { showBrowserNotification } from "@/lib/browser-notifications";

vi.mock("@/lib/browser-notifications", () => ({ showBrowserNotification: vi.fn().mockResolvedValue("skipped") }));
vi.mock("@/lib/notification-sound", () => ({ playTurnCompleteSound: vi.fn() }));
let rows: InboxNotice[];
let fail = false;
const requestMutation = vi.fn(async (_action: string, payload: Record<string, unknown>) => {
  const values = payload.values as { category?: string; ids?: string[]; id?: string };
  if (payload.action === "inbox.open") return { session_key: rows.find((item) => item.id === values.id)?.session_key ?? null };
  if (payload.action === "inbox.read") {
    rows = rows.map((item) => (!values.ids || values.ids.includes(item.id)) && (!values.category || item.category === values.category) ? { ...item, read_at: Date.now() } : item);
    return { ok: true };
  }
  if (fail) throw new Error("Notification storage unavailable");
  return { items: rows.filter((item) => !values.category || item.category === values.category),
    unread: Object.fromEntries(["operations", "conversations", "system"].map((name) => [name, rows.filter((item) => item.category === name && !item.read_at).length])),
    latest_seq: Math.max(0, ...rows.map((item) => item.seq)), next_before: null };
});
function notice(id: number, category: InboxNotice["category"], kind: string, body: string): InboxNotice {
  return { id: String(id), seq: id, category, kind, body, session_key: "websocket:one", status: kind === "question" ? "pending" : "succeeded", data: {}, created_at: Date.now(), read_at: null };
}
function view(onSelect = vi.fn(), connection = { status: "open", onStatus: (handler: (status: string) => void) => { handler("open"); return () => {}; } }) {
  return render(<ClientProvider client={{ requestMutation, ...connection } as unknown as CirnoClient} token="test">
    <InboxProvider><InboxView onBack={vi.fn()} onSelect={onSelect} onSettings={vi.fn()} /></InboxProvider>
  </ClientProvider>);
}
beforeEach(async () => {
  await setAppLanguage("en");
  window.history.replaceState(null, "", "#/inbox");
  rows = [notice(3, "system", "compaction", "Provider timeout"), notice(2, "conversations", "message", "Result available"), notice(1, "operations", "question", "Which dataset should I use?")];
  fail = false;
  vi.clearAllMocks();
});
afterEach(() => { cleanup(); });

it("shows three category pages and marks read without resolving a question", async () => {
  const select = vi.fn();
  view(select);
  await screen.findByText("Which dataset should I use?");
  fireEvent.click(screen.getByRole("tab", { name: /Actions/ }));
  await waitFor(() => expect(screen.queryByText("Result available")).not.toBeInTheDocument());
  expect(window.location.hash).toBe("#/inbox?category=operations");
  fireEvent.click(screen.getByRole("button", { name: /^Mark read$/ }));
  await waitFor(() => expect(rows.find((row) => row.id === "1")?.read_at).not.toBeNull());
  expect(rows.find((row) => row.id === "1")?.status).toBe("pending");
  fireEvent.click(screen.getByRole("button", { name: "Answer in conversation" }));
  await waitFor(() => expect(select).toHaveBeenCalledWith("websocket:one"));
});

it("opens a category URL directly and renders the actual error reason", async () => {
  window.history.replaceState(null, "", "#/inbox?category=system");
  view();
  expect(await screen.findByText("Provider timeout")).toBeInTheDocument();
  expect(screen.queryByText("Which dataset should I use?")).not.toBeInTheDocument();
});

it("does not alert for old history and alerts only new records with their category", async () => {
  view();
  await screen.findByText("Result available");
  expect(showBrowserNotification).not.toHaveBeenCalled();
  rows.unshift(notice(4, "operations", "question", "Which method?"));
  act(() => window.dispatchEvent(new Event("focus")));
  await waitFor(() => expect(showBrowserNotification).toHaveBeenCalledWith("An action needs your attention.", expect.objectContaining({ category: "operations", key: "inbox:4" })));
});

it("reports inbox loading failures instead of displaying an empty success state", async () => {
  fail = true;
  view();
  expect(await screen.findByRole("alert")).toHaveTextContent("Notification storage unavailable");
  expect(screen.queryByText("No notifications here")).not.toBeInTheDocument();
});

it("waits for the authenticated connection before loading and refreshes immediately on reconnect", async () => {
  let statusChanged: (status: string) => void = () => {};
  view(vi.fn(), { status: "connecting", onStatus: (handler) => { statusChanged = handler; return () => {}; } });
  expect(requestMutation).not.toHaveBeenCalled();
  act(() => statusChanged("open"));
  expect(await screen.findByText("Result available")).toBeInTheDocument();
  act(() => statusChanged("reconnecting"));
  rows.unshift(notice(4, "system", "dream", "New memory results"));
  act(() => statusChanged("open"));
  expect(await screen.findByText("New memory results")).toBeInTheDocument();
});
