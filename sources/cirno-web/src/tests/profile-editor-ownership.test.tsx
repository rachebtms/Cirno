import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useProfileFile } from "@/features/profile/model/useProfileFile";
import { useTextEditor } from "@/features/settings/shared/useTextEditor";
import type { WebUIMutationTransport } from "@/lib/api";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function connection() {
  const requestMutation = vi.fn(async (_method: string, { name, content }: Record<string, string>) => ({
    name, file: `${name}.md`, content: content ?? "Stored text", revision: "rev-1",
  }));
  return { client: { requestMutation } as unknown as WebUIMutationTransport, requestMutation };
}
function profile() {
  const first = connection();
  const view = renderHook(({ client, name }) => useProfileFile(client, name), {
    initialProps: { client: first.client, name: "memory" },
  });
  return { ...view, first };
}
it.each(["connection", "file", "unmount"])("rejects a retired editor read after %s replacement", async mode => {
  const view = profile();
  await waitFor(() => expect(view.result.current.value).not.toBeNull());
  const read = view.result.current.loadForEdit;
  const calls = view.first.requestMutation.mock.calls.length;
  if (mode === "unmount") view.unmount();
  else view.rerender({ client: mode === "connection" ? connection().client : view.first.client, name: mode === "file" ? "soul" : "memory" });
  await expect(read()).rejects.toThrow();
  expect(view.first.requestMutation).toHaveBeenCalledTimes(calls + (mode === "file" ? 1 : 0));
});
it.each(["connection", "file", "unmount"])("rejects a retired editor save after %s replacement", async mode => {
  const view = profile();
  await act(() => view.result.current.loadForEdit());
  const save = view.result.current.save;
  if (mode === "unmount") view.unmount();
  else view.rerender({ client: mode === "connection" ? connection().client : view.first.client, name: mode === "file" ? "soul" : "memory" });
  await expect(save("must not write")).rejects.toThrow();
  expect(view.first.requestMutation.mock.calls.filter(([method]) => method === "settings.profile.update")).toHaveLength(0);
});
it("requires the replacement connection's own editor snapshot", async () => {
  const view = profile();
  await act(() => view.result.current.loadForEdit());
  const next = connection();
  view.rerender({ client: next.client, name: "memory" });
  await expect(view.result.current.save("old draft")).rejects.toThrow();
  expect(view.first.requestMutation.mock.calls.filter(([method]) => method === "settings.profile.update")).toHaveLength(0);
  expect(next.requestMutation.mock.calls.filter(([method]) => method === "settings.profile.update")).toHaveLength(0);
});
it("does not return a superseded opening as a usable draft", async () => {
  const view = profile();
  await waitFor(() => expect(view.result.current.value).not.toBeNull());
  const old = deferred<{ name: string; file: string; content: string; revision: string }>();
  view.first.requestMutation.mockImplementationOnce(() => old.promise);
  const opening = view.result.current.loadForEdit();
  const rejected = expect(opening).rejects.toThrow();
  await act(() => view.result.current.loadForEdit());
  await act(async () => { old.resolve({ name: "memory", file: "memory.md", content: "old", revision: "old" }); await rejected; });
});
it("requires a successful new read after an editor-opening read fails", async () => {
  const view = profile();
  await act(() => view.result.current.loadForEdit());
  view.first.requestMutation.mockRejectedValueOnce(new Error("read failed"));
  await expect(view.result.current.loadForEdit()).rejects.toThrow("read failed");
  await expect(view.result.current.save("must not use earlier revision")).rejects.toThrow();
  expect(view.first.requestMutation.mock.calls.filter(([method]) => method === "settings.profile.update")).toHaveLength(0);
});
it("settles an accepted old save without replacing the new connection's displayed file", async () => {
  const view = profile();
  await act(() => view.result.current.loadForEdit());
  const saved = deferred<{ name: string; file: string; content: string; revision: string }>();
  view.first.requestMutation.mockImplementationOnce(() => saved.promise);
  let pending!: Promise<void>;
  act(() => { pending = view.result.current.save("accepted old change"); });
  const next = connection();
  view.rerender({ client: next.client, name: "memory" });
  await waitFor(() => expect(view.result.current.value?.content).toBe("Stored text"));
  await act(async () => {
    saved.resolve({ name: "memory", file: "old.md", content: "accepted old change", revision: "rev-2" });
    await pending;
  });
  expect(view.result.current.value?.content).toBe("Stored text");
});
it("does not replace a newer editor opening with an earlier save acknowledgement", async () => {
  const view = profile();
  await act(() => view.result.current.loadForEdit());
  const saved = deferred<{ name: string; file: string; content: string; revision: string }>();
  view.first.requestMutation.mockImplementationOnce(() => saved.promise);
  let pending!: Promise<void>;
  act(() => { pending = view.result.current.save("first"); });
  view.first.requestMutation.mockResolvedValueOnce({ name: "memory", file: "memory.md", content: "second opening", revision: "rev-current" });
  await act(() => view.result.current.loadForEdit());
  await act(async () => {
    saved.resolve({ name: "memory", file: "memory.md", content: "first", revision: "rev-old" });
    await pending;
    await view.result.current.save("second");
  });
  expect(view.first.requestMutation).toHaveBeenLastCalledWith("settings.profile.update", { name: "memory", content: "second", revision: "rev-current" });
});
it("keeps the editor snapshot available after a rejected save for an explicit retry", async () => {
  const view = profile();
  await act(() => view.result.current.loadForEdit());
  view.first.requestMutation.mockRejectedValueOnce(new Error("disk write rejected"));
  await expect(view.result.current.save("retry me")).rejects.toThrow("disk write rejected");
  await act(() => view.result.current.save("retry me"));
  expect(view.first.requestMutation).toHaveBeenLastCalledWith("settings.profile.update", { name: "memory", content: "retry me", revision: "rev-1" });
});
it("admits only one text-editor submission before React publishes the busy state", async () => {
  const result = deferred<void>(), onSave = vi.fn(() => result.promise);
  const view = renderHook(() => useTextEditor({ value: "draft", json: false, onSave }));
  act(() => view.result.current.changeOpen(true));
  let first!: Promise<void>, second!: Promise<void>;
  act(() => { first = view.result.current.save(); second = view.result.current.save(); });
  expect(onSave).toHaveBeenCalledTimes(1);
  await act(async () => { result.resolve(); await Promise.all([first, second]); });
  expect(view.result.current.open).toBe(false);
});
it("rejects a retained editor action after unmount without submitting", async () => {
  const onSave = vi.fn();
  const view = renderHook(() => useTextEditor({ value: "draft", json: false, onSave }));
  act(() => view.result.current.changeOpen(true));
  const save = view.result.current.save;
  view.unmount();
  await save();
  expect(onSave).not.toHaveBeenCalled();
});
it("keeps a failed save's draft and admits one explicit retry", async () => {
  const onSave = vi.fn().mockRejectedValueOnce(new Error("write failed")).mockResolvedValueOnce(undefined);
  const view = renderHook(() => useTextEditor({ value: "draft", json: false, onSave }));
  act(() => view.result.current.changeOpen(true));
  await act(() => view.result.current.save());
  expect(view.result.current.open).toBe(true);
  expect(view.result.current.draft).toBe("draft");
  expect(view.result.current.error).toBe("write failed");
  await act(() => view.result.current.save());
  expect(view.result.current.open).toBe(false);
  expect(onSave).toHaveBeenCalledTimes(2);
});
it("reports a synchronous editor-load failure and allows a fresh opening to retry", async () => {
  const loadValue = vi.fn<() => Promise<string>>().mockImplementationOnce(() => { throw new Error("connection changed"); }).mockResolvedValue("fresh");
  const view = renderHook(() => useTextEditor({ value: "stored", json: false, loadValue, onSave: vi.fn() }));
  expect(() => act(() => view.result.current.changeOpen(true))).not.toThrow();
  await waitFor(() => expect(view.result.current.error).toBe("connection changed"));
  expect(view.result.current.loadFailed).toBe(true);
  expect(view.result.current.loading).toBe(false);
  act(() => { view.result.current.changeOpen(false); view.result.current.changeOpen(true); });
  await waitFor(() => expect(view.result.current.draft).toBe("fresh"));
});
