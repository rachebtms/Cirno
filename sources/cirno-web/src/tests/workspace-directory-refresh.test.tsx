import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchWorkspaces } from "@/lib/api";
import { useWorkspaceDirectoryCatalog } from "@/app/useWorkspaceDirectoryCatalog";
import type { WorkspacesPayload } from "@/lib/contracts/workspaces";

vi.mock("@/lib/api", () => ({ fetchWorkspaces: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

function pending<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
const catalog = (path: string): WorkspacesPayload => ({
  schema_version: 1,
  default_access_mode: "default",
  default_scope: { project_path: path, access_mode: "restricted" },
  controls: { can_change_project: true },
});

describe("working-directory catalog refresh", () => {
  it("retains accepted data on failure and clears the visible error only after a successful retry", async () => {
    const onLoad = vi.fn();
    vi.mocked(fetchWorkspaces)
      .mockResolvedValueOnce(catalog("/first"))
      .mockRejectedValueOnce(new Error("Directory database unavailable"))
      .mockResolvedValueOnce(catalog("/restored"));
    const { result } = renderHook(() =>
      useWorkspaceDirectoryCatalog(() => "token", onLoad),
    );
    await act(() => result.current.refresh());
    await act(() => result.current.refresh());
    expect(onLoad).toHaveBeenCalledTimes(1);
    expect(onLoad).toHaveBeenLastCalledWith(catalog("/first"));
    expect(result.current.error).toBe("Directory database unavailable");
    expect(result.current.pending).toBe(false);
    await act(() => result.current.refresh());
    expect(onLoad).toHaveBeenLastCalledWith(catalog("/restored"));
    expect(result.current.error).toBeNull();
  });

  it.each(["success", "failure"])(
    "ignores a late %s from an earlier request after reconnect",
    async (outcome) => {
      const old = pending<WorkspacesPayload>();
      const current = pending<WorkspacesPayload>();
      vi.mocked(fetchWorkspaces)
        .mockReturnValueOnce(old.promise)
        .mockReturnValueOnce(current.promise);
      const onLoad = vi.fn();
      const { result } = renderHook(() =>
        useWorkspaceDirectoryCatalog(() => "token", onLoad),
      );
      let first!: Promise<void>;
      let second!: Promise<void>;
      act(() => {
        first = result.current.refresh();
        second = result.current.refresh();
      });
      expect(result.current.pending).toBe(true);
      await act(async () => {
        current.resolve(catalog("/current"));
        await second;
      });
      await act(async () => {
        if (outcome === "success") old.resolve(catalog("/old"));
        else old.reject(new Error("Old connection failed"));
        await first;
      });
      expect(onLoad).toHaveBeenCalledTimes(1);
      expect(onLoad).toHaveBeenLastCalledWith(catalog("/current"));
      expect(result.current.error).toBeNull();
      expect(result.current.pending).toBe(false);
    },
  );

  it("does not publish a pending response after its workspace owner unmounts", async () => {
    const request = pending<WorkspacesPayload>();
    vi.mocked(fetchWorkspaces).mockReturnValueOnce(request.promise);
    const onLoad = vi.fn();
    const { result, unmount } = renderHook(() =>
      useWorkspaceDirectoryCatalog(() => "token", onLoad),
    );
    let refresh!: Promise<void>;
    act(() => {
      refresh = result.current.refresh();
    });
    unmount();
    request.resolve(catalog("/late"));
    await refresh;
    expect(onLoad).not.toHaveBeenCalled();
  });
});
