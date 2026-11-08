import { queuedPromptStoreFor } from "@/features/composer/queue/store";
import { canAutoSendQueuedPrompt, getQueuedPromptPageId } from "@/features/composer/contracts";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useState } from "react";
import { toast } from "@heroui/react";
import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { acceptComposerDraft, clearStoredComposerDrafts, ComposerDraftStore, type ComposerDraft } from "@/lib/composer-draft";
import { clearBrowserDrafts } from "@/app/clearBrowserDrafts";

const key = "websocket:draft-recovery";
const storageKey = `cirno.composer-draft.v1.${key}`;
const saved: ComposerDraft = { text: "Review @other", quotedContext: "Saved evidence", sessionMentions: [{ name: "other", session_key: "websocket:other", title: "Other research" }],
  attachments: [{ path: "/workspace/paper.txt", name: "paper.txt", kind: "file", size: 10, mime: "text/plain", url: "" }] };
afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

it("does not erase a failed restore and recovers text, quote, attachment and target through Retry", async () => {
  new ComposerDraftStore().set(key, saved, true);
  const original = localStorage.getItem.bind(localStorage);
  const read = vi.spyOn(localStorage, "getItem").mockImplementation(name => {
    if (name === storageKey) throw new Error("Draft storage disabled");
    return original(name);
  });
  const remove = vi.spyOn(localStorage, "removeItem");
  const onSend = vi.fn(() => true);
  function Editor() {
    const [store] = useState(() => new ComposerDraftStore());
    const [quote, setQuote] = useState<string | null>(null);
    return <ThreadComposer draftKey={key} draftStore={store} persistDraft quotedContext={quote} onQuotedContextChange={setQuote} onSend={onSend} />;
  }
  render(<Editor />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not restore");
  expect(remove).not.toHaveBeenCalledWith(storageKey);
  expect(JSON.parse(original(storageKey)!)).toMatchObject({ text: saved.text });
  read.mockRestore();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(screen.getByRole("textbox", { name: "Message input" })).toHaveValue(saved.text);
  expect(screen.getByText("Saved evidence")).toBeVisible();
  expect(screen.getByText("paper.txt")).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(onSend).toHaveBeenCalledWith(saved.text, [expect.objectContaining({ media: { path: "/workspace/paper.txt", name: "paper.txt" } })],
    expect.objectContaining({ quotedContext: saved.quotedContext, sessionMentions: saved.sessionMentions }));
});

it("retains the current revision across remounts when saving fails and persists it on retry", async () => {
  const store = new ComposerDraftStore();
  store.set(key, { ...saved, attachments: [] }, true);
  const write = vi.spyOn(localStorage, "setItem").mockImplementation(() => { throw new Error("Draft quota exceeded"); });
  const props = { draftKey: key, draftStore: store, persistDraft: true, onSend: vi.fn() };
  const view = render(<ThreadComposer {...props} />);
  fireEvent.change(screen.getByRole("textbox", { name: "Message input" }), { target: { value: "Latest research input" } });
  expect(await screen.findByRole("alert")).toHaveTextContent("Keep this page open and retry");
  view.unmount();
  render(<ThreadComposer {...props} />);
  expect(screen.getByRole("textbox", { name: "Message input" })).toHaveValue("Latest research input");
  write.mockRestore();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(new ComposerDraftStore().get(key, true)?.text).toBe("Latest research input");
});

it("does not restore an accepted draft after local removal fails, and retries removal explicitly", async () => {
  const store = new ComposerDraftStore();
  const draft = { ...saved, text: "Send this once", attachments: [], quotedContext: null, sessionMentions: [] };
  store.set(key, draft, true);
  const remove = vi.spyOn(localStorage, "removeItem").mockImplementation(() => { throw new Error("Draft removal denied"); });
  const onSend = vi.fn(() => true);
  const props = { draftKey: key, draftStore: store, persistDraft: true, onSend };
  const view = render(<ThreadComposer {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(onSend).toHaveBeenCalledTimes(1);
  expect(await screen.findByRole("alert")).toHaveTextContent("saved draft could not be removed");
  view.unmount();
  render(<ThreadComposer {...props} />);
  expect(screen.getByRole("textbox", { name: "Message input" })).toHaveValue("");
  remove.mockRestore();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(localStorage.getItem(storageKey)).toBeNull();
  expect(onSend).toHaveBeenCalledTimes(1);
});

it("never clears a newer revision when an older send is accepted", () => {
  const store = new ComposerDraftStore();
  store.set(key, saved, true);
  const submitted = store.get(key);
  store.set(key, { ...saved, text: "New instructions" }, true);
  expect(acceptComposerDraft(store, key, submitted)).toBe(false);
  expect(store.get(key)?.text).toBe("New instructions");
  expect(JSON.parse(localStorage.getItem(storageKey)!).text).toBe("New instructions");
});

it("attempts every saved draft cleanup and reports failure without blocking account transitions", () => {
  localStorage.setItem(storageKey, "saved");
  localStorage.setItem("cirno.composer-draft.v1.other", "saved");
  const remove = localStorage.removeItem.bind(localStorage);
  vi.spyOn(localStorage, "removeItem").mockImplementation(name => {
    if (name === storageKey) throw new Error("Storage cleanup denied");
    remove(name);
  });
  expect(() => clearStoredComposerDrafts()).toThrow(AggregateError);
  expect(localStorage.getItem("cirno.composer-draft.v1.other")).toBeNull();
  const notice = vi.spyOn(toast, "danger").mockReturnValue("cleanup-notice");
  expect(() => clearBrowserDrafts()).not.toThrow();
  expect(notice).toHaveBeenCalledWith("Could not clear saved drafts from this browser.", expect.objectContaining({ description: "Storage cleanup denied", timeout: 0 }));
});

it("revokes automatic waiting-message delivery on account transitions without discarding its contents", () => {
  const store = queuedPromptStoreFor("cirno.webui.composerQueuedGuidance.v1:account-boundary");
  const unsubscribe = store.subscribe(() => {});
  store.set({ id: "waiting", text: "Continue this research", autoSendPageId: getQueuedPromptPageId(), autoAfterTurnId: "old-turn" });
  expect(canAutoSendQueuedPrompt(store.getSnapshot().prompt!)).toBe(true);
  clearBrowserDrafts();
  expect(store.getSnapshot().prompt).toMatchObject({ text: "Continue this research", autoPaused: true });
  expect(canAutoSendQueuedPrompt(store.getSnapshot().prompt!)).toBe(false);
  unsubscribe();
});
