import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useProjects } from "@/features/conversations/projects/useProjects";
import type { CirnoClient } from "@/lib/cirno-client";

afterEach(cleanup);
const project = { id: "research", name: "Research", working_directory: "/same" };
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function connection() {
  let status!: (value: string) => void;
  let update!: (chat: string, scope: string) => void;
  const request = vi.fn().mockResolvedValue({ projects: [project] });
  const client = {
    requestMutation: request,
    onStatus: (handler: typeof status) => { status = handler; return () => {}; },
    onSessionUpdate: (handler: typeof update) => { update = handler; return () => {}; },
  } as unknown as CirnoClient;
  return { client, request, open: () => status("open"), update: () => update("cirno", "projects") };
}
function fixture() {
  const first = connection(), refreshSessions = vi.fn().mockResolvedValue(undefined);
  const view = renderHook(({ client }) => useProjects(client, refreshSessions), { initialProps: { client: first.client } });
  return { ...view, first, refreshSessions };
}

it("loads the project domain directly without duplicating the session owner's event refresh", async () => {
  const state = fixture();
  await act(async () => state.first.open());
  expect(state.first.request).toHaveBeenCalledExactlyOnceWith("instance.action", { action: "projects.list" });
  expect(state.result.current.projects).toEqual([project]);
  await act(async () => state.first.update());
  expect(state.refreshSessions).not.toHaveBeenCalled();
});

it("ignores an old connection's delayed list and releases its mounted callbacks", async () => {
  const state = fixture(), pending = deferred<{ projects: typeof project[] }>();
  state.first.request.mockReturnValueOnce(pending.promise);
  act(() => state.first.open());
  const oldSave = state.result.current.save, second = connection();
  state.rerender({ client: second.client });
  await act(async () => second.open());
  await act(async () => pending.resolve({ projects: [{ ...project, name: "Old instance" }] }));
  expect(state.result.current.projects).toEqual([project]);
  await act(async () => oldSave({ name: "Old callback", working_directory: "" }));
  expect(state.first.request).toHaveBeenCalledTimes(1);
});

it("keeps a failed read visible with prior records and permits explicit retry", async () => {
  const state = fixture();
  await act(async () => state.first.open());
  state.first.request.mockRejectedValueOnce(new Error("Projects unavailable"));
  await act(async () => state.first.update());
  expect(state.result.current.error).toBe("Projects unavailable");
  expect(state.result.current.projects).toEqual([project]);
  await act(async () => state.result.current.retry());
  expect(state.result.current.error).toBeNull();
});

it.each(["save", "remove"] as const)("propagates a failed %s to its editor without treating it as success", async kind => {
  const state = fixture();
  await act(async () => state.first.open());
  state.first.request.mockRejectedValueOnce(new Error("Project write unavailable"));
  await act(async () => {
    const request = kind === "save" ? state.result.current.save({ id: project.id, name: "Updated", working_directory: "/new" }) : state.result.current.remove(project.id);
    await expect(request).rejects.toThrow("Project write unavailable");
  });
  expect(state.result.current.projects).toEqual([project]);
  expect(state.refreshSessions).not.toHaveBeenCalled();
});

it("invalidates an older list when saving and fetches the current canonical projects", async () => {
  const state = fixture(), older = deferred<{ projects: typeof project[] }>();
  state.first.request.mockReturnValueOnce(older.promise)
    .mockResolvedValueOnce({ project, projects: [project] })
    .mockResolvedValueOnce({ projects: [{ ...project, name: "Canonical" }] });
  act(() => state.first.open());
  await act(async () => state.result.current.save({ id: project.id, name: "Submitted", working_directory: "/same" }));
  await act(async () => older.resolve({ projects: [{ ...project, name: "Old" }] }));
  expect(state.result.current.projects[0].name).toBe("Canonical");
  expect(state.first.request).toHaveBeenNthCalledWith(2, "instance.action", { action: "projects.save", values: { id: project.id, name: "Submitted", working_directory: "/same" } });
});

it("keeps a successful write separate from a failed follow-up read so Retry does not create twice", async () => {
  const state = fixture();
  state.first.request.mockResolvedValueOnce({ project, projects: [project] })
    .mockRejectedValueOnce(new Error("Project list unavailable"));
  await act(async () => state.result.current.save({ name: "Research", working_directory: "/same" }));
  expect(state.result.current.error).toBe("Project list unavailable");
  await act(async () => state.result.current.retry());
  expect(state.first.request.mock.calls.map(([, args]) => args.action)).toEqual(["projects.save", "projects.list", "projects.list"]);
  expect(state.result.current.projects).toEqual([project]);
  expect(state.result.current.error).toBeNull();
});

it("does not refresh the replacement connection after an old write acknowledgement", async () => {
  const state = fixture(), older = deferred<object>();
  state.first.request.mockReturnValueOnce(older.promise);
  let request!: Promise<void>;
  act(() => { request = state.result.current.remove(project.id); });
  const second = connection();
  state.rerender({ client: second.client });
  await act(async () => { older.resolve({ projects: [] }); await request; });
  expect(second.request).not.toHaveBeenCalled();
  expect(state.first.request).toHaveBeenCalledTimes(1);
  expect(state.refreshSessions).not.toHaveBeenCalled();
});

it("serializes membership changes and retries the exact failed assignment", async () => {
  const state = fixture(), pending = deferred<object>();
  state.first.request.mockReturnValueOnce(pending.promise);
  let request!: ReturnType<typeof state.result.current.assign>;
  act(() => { request = state.result.current.assign("websocket:worker", project.id); });
  expect(state.result.current.assigning).toBe(true);
  await act(async () => state.result.current.assign("websocket:worker", null));
  expect(state.first.request).toHaveBeenCalledTimes(1);
  await act(async () => { pending.resolve({ ok: true }); await request; });
  state.first.request.mockRejectedValueOnce(new Error("Membership unavailable"));
  await act(async () => state.result.current.assign("websocket:worker", null));
  expect(state.result.current.error).toBe("Membership unavailable");
  await act(async () => state.result.current.retry());
  expect(state.first.request).toHaveBeenLastCalledWith("instance.action", { action: "projects.assign", values: { session_key: "websocket:worker", project_id: null } });
  expect(state.result.current.error).toBeNull();
  expect(state.refreshSessions).toHaveBeenCalledTimes(2);
});
