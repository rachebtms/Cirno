import { act, renderHook } from "@testing-library/react";
import { useState } from "react";
import { expect, it, vi } from "vitest";
import { useNavigationActions } from "@/app/useNavigationActions";
import type { useWorkspaceState } from "@/app/useWorkspaceState";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { CirnoClient } from "@/lib/cirno-client";

type Pending = ReturnType<typeof useWorkspaceState>["pendingDelete"];
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }
function owner() { return { client: {} as CirnoClient, deleteChat: vi.fn().mockResolvedValue({ deleted: true }),
  getSessionAutomations: vi.fn().mockResolvedValue([]), filePreviewStore: { delete: vi.fn() }, draftStore: { delete: vi.fn() } }; }
function mount(value = owner()) {
  const view = renderHook(({ owner }) => {
    const [pendingDelete, setPendingDelete] = useState<Pending>(null);
    const workspaceState = { ...owner, pendingDelete, setPendingDelete, sidebarState: { title_overrides: {} },
      t: (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key } as unknown as ReturnType<typeof useWorkspaceState>;
    return { ...useNavigationActions({ workspaceState }), pending: pendingDelete };
  }, { initialProps: { owner: value } });
  return { ...view, owner: value, show: async (keys: string[], callback = vi.fn()) => {
    await act(async () => view.result.current.onRequestDeleteMany(keys.map(key => ({ key, label: key })), callback));
    return callback;
  } };
}
it("keeps the latest deletion request when automation preflights return out of order", async () => {
  const first = deferred<SessionAutomationJob[]>(), second = deferred<SessionAutomationJob[]>();
  const context = owner(); context.getSessionAutomations.mockImplementation(key => key === "a" ? first.promise : second.promise);
  const view = mount(context), oldDecision = vi.fn(), nextDecision = vi.fn();
  let a!: Promise<void>, b!: Promise<void>;
  act(() => { a = view.result.current.onRequestDeleteMany([{ key: "a", label: "A" }], oldDecision); b = view.result.current.onRequestDeleteMany([{ key: "b", label: "B" }], nextDecision); });
  await act(async () => { second.resolve([]); await b; first.resolve([]); await a; });
  expect(view.result.current.pending?.items.map(item => item.key)).toEqual(["b"]);
  expect(oldDecision).toHaveBeenCalledExactlyOnceWith(false);
  expect(nextDecision).not.toHaveBeenCalled();
});
it("does not discard local drafts or close the confirmation without a deletion receipt", async () => {
  const view = mount(); view.owner.deleteChat.mockResolvedValue({ deleted: false });
  await view.show(["a"]);
  await act(async () => view.result.current.onConfirmDelete());
  expect(view.owner.draftStore.delete).not.toHaveBeenCalled();
  expect(view.owner.filePreviewStore.delete).not.toHaveBeenCalled();
  expect(view.result.current.pending?.items[0].key).toBe("a");
  expect(view.result.current.deleteError).toBeTruthy();
});
it("ignores an earlier confirmation after a different deletion is selected", async () => {
  const view = mount();
  await view.show(["a"]);
  const oldConfirm = view.result.current.onConfirmDelete;
  await view.show(["b"]);
  await act(async () => oldConfirm());
  expect(view.owner.deleteChat).not.toHaveBeenCalled();
  expect(view.result.current.pending?.items[0].key).toBe("b");
});
it("does not post a retired automation lookup into the replacement connection", async () => {
  const first = deferred<SessionAutomationJob[]>(), context = owner();
  context.getSessionAutomations.mockImplementation(() => first.promise);
  const view = mount(context), decide = vi.fn();
  let request!: Promise<void>;
  act(() => { request = view.result.current.onRequestDeleteMany([{ key: "a", label: "A" }], decide); });
  view.rerender({ owner: owner() });
  await act(async () => { first.resolve([]); await request; });
  expect(view.result.current.pending).toBeNull();
  expect(decide).toHaveBeenCalledExactlyOnceWith(false);
});
it("does not execute an old confirmation after changing connections", async () => {
  const view = mount(); await view.show(["a"]);
  const confirm = view.result.current.onConfirmDelete;
  const next = owner(); view.rerender({ owner: next });
  await act(async () => confirm());
  expect(view.owner.deleteChat).not.toHaveBeenCalled();
  expect(next.deleteChat).not.toHaveBeenCalled();
  expect(view.result.current.pending).toBeNull();
});
it("settles the accepted deletion but stops its old batch and preserves a new confirmation", async () => {
  const receipt = deferred<{ deleted: boolean }>(), view = mount();
  view.owner.deleteChat.mockImplementation(() => receipt.promise);
  await view.show(["a", "b"]);
  let deleting!: Promise<void>;
  act(() => { deleting = view.result.current.onConfirmDelete(); });
  const next = owner(); view.rerender({ owner: next });
  await view.show(["new"]);
  await act(async () => { receipt.resolve({ deleted: true }); await deleting; });
  expect(view.owner.deleteChat).toHaveBeenCalledTimes(1);
  expect(view.owner.draftStore.delete).not.toHaveBeenCalled();
  expect(view.result.current.pending?.items[0].key).toBe("new");
  expect(view.result.current.deleteBusy).toBe(false);
});
it("retains only the remaining items after a partial failure and retries without notifying twice", async () => {
  const view = mount(), decision = vi.fn();
  view.owner.deleteChat.mockResolvedValueOnce({ deleted: true }).mockRejectedValueOnce(new Error("Storage unavailable")).mockResolvedValue({ deleted: true });
  await view.show(["a", "b", "b", "c"], decision);
  await act(async () => view.result.current.onConfirmDelete());
  expect(view.result.current.pending?.items.map(item => item.key)).toEqual(["b", "c"]);
  expect(view.owner.draftStore.delete).toHaveBeenCalledExactlyOnceWith("a");
  await act(async () => view.result.current.onConfirmDelete());
  expect(view.result.current.pending).toBeNull();
  expect(decision).toHaveBeenCalledExactlyOnceWith(true);
  expect(view.owner.deleteChat.mock.calls.map(([key]) => key)).toEqual(["a", "b", "b", "c"]);
});
it("cancels a confirmation once and ignores its retained cancel callback after replacement", async () => {
  const view = mount(), first = vi.fn(), second = vi.fn();
  await view.show(["a"], first);
  const oldCancel = view.result.current.onCancelDelete;
  await view.show(["b"], second);
  act(() => oldCancel());
  expect(view.result.current.pending?.items[0].key).toBe("b");
  act(() => { view.result.current.onCancelDelete(); view.result.current.onCancelDelete(); });
  expect(view.result.current.pending).toBeNull();
  expect(first).toHaveBeenCalledExactlyOnceWith(false);
  expect(second).toHaveBeenCalledExactlyOnceWith(false);
});
it("declines a new request during an accepted deletion without stranding its caller", async () => {
  const receipt = deferred<{ deleted: boolean }>(), view = mount();
  view.owner.deleteChat.mockImplementation(() => receipt.promise);
  await view.show(["a"]);
  let deleting!: Promise<void>;
  act(() => { deleting = view.result.current.onConfirmDelete(); });
  const decision = await view.show(["b"]);
  expect(decision).toHaveBeenCalledExactlyOnceWith(false);
  expect(view.result.current.pending?.items[0].key).toBe("a");
  await act(async () => { receipt.resolve({ deleted: true }); await deleting; });
  expect(view.owner.deleteChat).toHaveBeenCalledTimes(1);
});
it("requests a new confirmation when linked automations appear during deletion", async () => {
  const view = mount();
  const automation = { id: "job", name: "Bound automation" };
  view.owner.deleteChat.mockResolvedValueOnce({ deleted: false, blocked_by_automations: true, automations: [automation] }).mockResolvedValue({ deleted: true });
  await view.show(["a"]);
  await act(async () => view.result.current.onConfirmDelete());
  expect(view.result.current.pending?.automations).toEqual([automation]);
  expect(view.owner.draftStore.delete).not.toHaveBeenCalled();
  await act(async () => view.result.current.onConfirmDelete());
  expect(view.owner.deleteChat).toHaveBeenLastCalledWith("a", { deleteAutomations: true });
  expect(view.result.current.pending).toBeNull();
});
