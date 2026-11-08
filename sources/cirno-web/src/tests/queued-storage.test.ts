import { afterEach, expect, it, vi } from "vitest";
import { queuedPromptStoreFor } from "@/features/composer/queue/store";

const key = (name: string) => `cirno.webui.composerQueuedGuidance.v1:storage-${name}`;
afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

it("retains an unpersisted waiting message across subscriber disposal and retries its write", () => {
  const store = queuedPromptStoreFor(key("quota"));
  const dispose = store.subscribe(() => {});
  const write = vi.spyOn(localStorage, "setItem").mockImplementation(() => { throw new DOMException("Quota exceeded", "QuotaExceededError"); });
  store.set({ id: "draft", text: "Keep these results" });
  expect(store.getSnapshot()).toMatchObject({ prompt: { text: "Keep these results" }, storageIssue: { action: "save", detail: "Quota exceeded" } });
  dispose();
  expect(queuedPromptStoreFor(key("quota"))).toBe(store);
  write.mockRestore();
  const unmount = store.subscribe(() => {});
  store.retryStorage();
  expect(store.getSnapshot().storageIssue).toBeNull();
  unmount();
  expect(queuedPromptStoreFor(key("quota")).getSnapshot().prompt?.text).toBe("Keep these results");
});

it("retains an accepted-send tombstone when durable removal fails instead of restoring a duplicate", () => {
  const store = queuedPromptStoreFor(key("remove"));
  const dispose = store.subscribe(() => {});
  const prompt = { id: "draft", text: "Send once" };
  store.set(prompt);
  const remove = vi.spyOn(localStorage, "removeItem").mockImplementation(() => { throw new Error("Storage unavailable"); });
  const send = vi.fn(() => true);
  store.send(prompt, send);
  expect(send).toHaveBeenCalledTimes(1);
  expect(store.getSnapshot()).toMatchObject({ prompt: null, storageIssue: { action: "save" } });
  dispose();
  expect(queuedPromptStoreFor(key("remove")).getSnapshot().prompt).toBeNull();
  remove.mockRestore();
  store.retryStorage();
  expect(localStorage.getItem(key("remove"))).toBeNull();
  expect(queuedPromptStoreFor(key("remove")).getSnapshot().storageIssue).toBeNull();
});

it("reports a failed restore and retries without overwriting the original stored draft", () => {
  localStorage.setItem(key("read"), JSON.stringify([{ id: "kept", text: "Original instruction" }]));
  const read = vi.spyOn(localStorage, "getItem").mockImplementation(() => { throw new Error("Storage disabled"); });
  const store = queuedPromptStoreFor(key("read"));
  expect(store.getSnapshot()).toMatchObject({ prompt: null, storageIssue: { action: "read", detail: "Storage disabled" } });
  read.mockRestore();
  store.retryStorage();
  expect(store.getSnapshot()).toMatchObject({ prompt: { text: "Original instruction", autoPaused: true }, storageIssue: null });
});

it("preserves malformed storage for repair and recovers after it is corrected", () => {
  localStorage.setItem(key("malformed"), "{broken");
  const store = queuedPromptStoreFor(key("malformed"));
  expect(store.getSnapshot().storageIssue?.action).toBe("read");
  expect(localStorage.getItem(key("malformed"))).toBe("{broken");
  localStorage.setItem(key("malformed"), JSON.stringify([{ id: "corrected", text: "Recovered" }]));
  store.retryStorage();
  expect(store.getSnapshot()).toMatchObject({ prompt: { text: "Recovered" }, storageIssue: null });
});

it("restores every stored contribution instead of silently discarding entries beyond twenty", () => {
  const prompts = Array.from({ length: 27 }, (_, index) => ({ id: String(index), text: `Finding ${index}` }));
  localStorage.setItem(key("long"), JSON.stringify(prompts));
  const restored = queuedPromptStoreFor(key("long")).getSnapshot().prompt!;
  expect(restored.text).toBe(prompts.map(prompt => prompt.text).join("\n"));
  expect(restored.autoPaused).toBe(true);
});
