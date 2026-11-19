import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useSkillDetail } from "@/features/skills/model/useSkillDetail";
import { useSkillHistory } from "@/features/skills/model/useSkillHistory";
import type { SkillService } from "@/features/skills/model/service";
import type { SkillDetail } from "@/lib/contracts/skills";
import type { WebUIMutationTransport } from "@/lib/api";
type HistoryResult = NonNullable<ReturnType<typeof useSkillHistory>["result"]>;
const skill: SkillDetail = { name: "first", source: "home", description: "Fixture", available: true, enabled: true, raw_markdown: "Instructions", requirements: null };
function service(): SkillService {
  return { read: vi.fn(async name => ({ ...skill, name })), update: vi.fn(), remove: vi.fn(async () => ({ skills: [], last_action: { name: "first", deleted: true, enabled: false } })), popular: vi.fn(), search: vi.fn(), trends: vi.fn(), install: vi.fn() };
}
function detail() {
  const api = service(), close = vi.fn();
  const view = renderHook(({ api, name }) => useSkillDetail(api, { ...skill, name }, close), { initialProps: { api, name: "first" } });
  return { ...view, api, close };
}
function historyClient() {
  const requestMutation = vi.fn(async (): Promise<HistoryResult> => ({ validation: { valid: true, errors: [] }, versions: [] }));
  return { client: { requestMutation } as unknown as WebUIMutationTransport, requestMutation };
}
it("does not carry a deletion confirmation into another Skill's detail", async () => {
  const view = detail();
  await waitFor(() => expect(view.result.current.read.value).not.toBeNull());
  act(() => view.result.current.requestDelete());
  view.rerender({ api: view.api, name: "second" });
  expect(view.result.current.deleting).toBe(false);
});
it.each(["requestDelete", "cancelDelete"] as const)("ignores retired detail %s callbacks", async action => {
  const view = detail();
  await waitFor(() => expect(view.result.current.read.value).not.toBeNull());
  const old = view.result.current;
  view.rerender({ api: view.api, name: "second" });
  if (action === "cancelDelete") act(() => view.result.current.requestDelete());
  act(() => old[action]());
  expect(view.result.current.deleting).toBe(action === "cancelDelete");
});
it.each(["cancel", "replace"])("does not delete through an earlier confirmation after %s", async action => {
  const view = detail();
  await waitFor(() => expect(view.result.current.read.value).not.toBeNull());
  act(() => view.result.current.requestDelete());
  const remove = view.result.current.remove;
  act(() => view.result.current.cancelDelete());
  if (action === "replace") act(() => view.result.current.requestDelete());
  await act(async () => { await remove(); });
  expect(view.api.remove).not.toHaveBeenCalled();
  expect(view.close).not.toHaveBeenCalled();
});
it("does not submit deletion without a current confirmation", async () => {
  const view = detail();
  await waitFor(() => expect(view.result.current.read.value).not.toBeNull());
  await act(async () => { await view.result.current.remove(); });
  expect(view.api.remove).not.toHaveBeenCalled();
});
it("does not close the replacement view after a synchronous Skills-change subscriber switches owners", async () => {
  const view = detail();
  await waitFor(() => expect(view.result.current.read.value).not.toBeNull());
  act(() => view.result.current.requestDelete());
  const { flushSync } = await import("react-dom");
  const { SKILLS_CHANGED_EVENT } = await import("@/lib/skill-events");
  const change = () => flushSync(() => view.rerender({ api: service(), name: "second" }));
  window.addEventListener(SKILLS_CHANGED_EVENT, change);
  try { await act(async () => { await view.result.current.remove(); }); }
  finally { window.removeEventListener(SKILLS_CHANGED_EVENT, change); }
  expect(view.api.remove).toHaveBeenCalledTimes(1);
  expect(view.close).not.toHaveBeenCalled();
});
it("locks an accepted deletion against same-frame cancellation and replacement confirmations", async () => {
  const view = detail();
  await waitFor(() => expect(view.result.current.read.value).not.toBeNull());
  let finish!: (value: Awaited<ReturnType<SkillService["remove"]>>) => void;
  vi.mocked(view.api.remove).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  act(() => view.result.current.requestDelete());
  const controls = view.result.current;
  let pending!: unknown;
  act(() => { pending = controls.remove(); controls.cancelDelete(); controls.requestDelete(); });
  expect(view.result.current.deleting).toBe(true);
  expect(view.api.remove).toHaveBeenCalledTimes(1);
  await act(async () => { finish({ skills: [], last_action: { name: "first", deleted: true, enabled: false } }); await pending; });
  expect(view.close).toHaveBeenCalledTimes(1);
  expect(view.result.current.deleting).toBe(false);
});
it("does not carry history draft/results back into a previously selected connection", async () => {
  const first = historyClient(), view = renderHook(useSkillHistory, { initialProps: first.client });
  act(() => view.result.current.changeName("first"));
  await act(() => view.result.current.validate());
  expect(view.result.current.result).not.toBeNull();
  view.rerender(historyClient().client);
  view.rerender(first.client);
  expect(view.result.current.name).toBe("");
  expect(view.result.current.result).toBeNull();
});
it("ignores a retired history-name setter", () => {
  const first = historyClient(), view = renderHook(useSkillHistory, { initialProps: first.client });
  const change = view.result.current.changeName;
  view.rerender(historyClient().client);
  act(() => view.result.current.changeName("current"));
  act(() => change("retired"));
  expect(view.result.current.name).toBe("current");
});
it("does not validate a name from an earlier rendered draft", async () => {
  const first = historyClient(), view = renderHook(useSkillHistory, { initialProps: first.client });
  act(() => view.result.current.changeName("first"));
  const validate = view.result.current.validate;
  act(() => view.result.current.changeName("second"));
  await act(async () => { await validate(); });
  expect(first.requestMutation).not.toHaveBeenCalled();
});
it("does not restore an old validation after the draft changes away and back", async () => {
  let finish!: (value: HistoryResult) => void;
  const first = historyClient();
  first.requestMutation.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const view = renderHook(useSkillHistory, { initialProps: first.client });
  act(() => view.result.current.changeName("first"));
  let pending!: unknown;
  act(() => { pending = view.result.current.validate(); });
  act(() => view.result.current.changeName("second"));
  act(() => view.result.current.changeName("first"));
  await act(async () => { finish({ validation: { valid: true, errors: [] }, versions: [] }); await pending; });
  expect(view.result.current.result).toBeNull();
});
it("settles an accepted history validation before allowing another draft to be validated", async () => {
  let finish!: (value: HistoryResult) => void;
  const first = historyClient();
  first.requestMutation.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const view = renderHook(useSkillHistory, { initialProps: first.client });
  act(() => view.result.current.changeName("first"));
  let pending!: unknown;
  act(() => { pending = view.result.current.validate(); });
  act(() => view.result.current.changeName("second"));
  await act(async () => { await view.result.current.validate(); });
  expect(first.requestMutation).toHaveBeenCalledTimes(1);
  await act(async () => { finish({ validation: { valid: true, errors: [] }, versions: [] }); await pending; });
  expect(view.result.current.result).toBeNull();
  await act(async () => { await view.result.current.validate(); });
  expect(first.requestMutation).toHaveBeenCalledTimes(2);
  expect(first.requestMutation).toHaveBeenLastCalledWith("instance.action", { action: "skills.validate", values: { name: "second" } });
  expect(view.result.current.result).not.toBeNull();
});
