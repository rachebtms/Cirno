import { act, cleanup, renderHook } from "@testing-library/react";
import { toast } from "@heroui/react";
import { afterEach, expect, it, vi } from "vitest";
import { useSettingsNavigation } from "@/features/settings/composition/useSettingsNavigation";
import type { SettingsController } from "@/features/settings/useSettingsController";
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
function deferred() {
    let resolve!: (value: boolean) => void;
    const promise = new Promise<boolean>(done => { resolve = done; });
    return { promise, resolve };
}
function fixture() {
    const commit = vi.fn().mockResolvedValue(true);
    const dirty = vi.fn().mockReturnValue(true);
    const clean = { needsCompletion: () => false, commit: async () => true };
    const controller = {
        client: {}, settings: { requires_restart: false }, activeSection: "models",
        selectSection: vi.fn(), modelEdits: { needsCompletion: dirty, commit }, safetyEdits: clean, webEdits: clean,
    } as unknown as SettingsController;
    const view = renderHook(({ owner }) => useSettingsNavigation(owner, false), { initialProps: { owner: controller } });
    return { ...view, controller, commit, dirty };
}
it("retains the latest destination when queued settings completions finish out of order", async () => {
    const first = deferred(), second = deferred();
    const state = fixture();
    state.commit.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    act(() => { state.result.current.selectSection("memory"); state.result.current.selectSection("providers"); });
    await act(async () => second.resolve(true));
    expect(state.controller.selectSection).toHaveBeenCalledExactlyOnceWith("providers");
    await act(async () => first.resolve(true));
    expect(state.controller.selectSection).toHaveBeenCalledTimes(1);
});
it("does not revive an older exit after an immediate navigation", async () => {
    const first = deferred(), leave = vi.fn();
    const state = fixture();
    state.commit.mockReturnValueOnce(first.promise);
    act(() => state.result.current.requestExit(leave));
    state.dirty.mockReturnValue(false);
    act(() => state.result.current.selectSection("memory"));
    await act(async () => first.resolve(true));
    expect(state.controller.selectSection).toHaveBeenCalledExactlyOnceWith("memory");
    expect(leave).not.toHaveBeenCalled();
});
it.each(["replacement", "unmount"])("ignores delayed exit completion after owner %s", async (change) => {
    const first = deferred(), leave = vi.fn();
    const state = fixture();
    state.commit.mockReturnValueOnce(first.promise);
    act(() => state.result.current.requestExit(leave));
    if (change === "replacement")
        state.rerender({ owner: { ...state.controller, client: {} } as SettingsController });
    else
        state.unmount();
    await act(async () => first.resolve(true));
    expect(leave).not.toHaveBeenCalled();
});
it("shows rejected completion and permits a new navigation attempt", async () => {
    const notice = vi.spyOn(toast, "danger").mockReturnValue("navigation-error");
    const state = fixture();
    state.commit.mockRejectedValueOnce(new Error("Cannot save settings"));
    await act(async () => state.result.current.selectSection("memory"));
    expect(notice).toHaveBeenCalledExactlyOnceWith("Cannot save settings", { timeout: 0 });
    expect(state.controller.selectSection).not.toHaveBeenCalled();
    await act(async () => state.result.current.selectSection("memory"));
    expect(state.controller.selectSection).toHaveBeenCalledExactlyOnceWith("memory");
});
it("invalidates a pending restart exit when a newer destination is selected", () => {
    const leave = vi.fn(), state = fixture();
    state.dirty.mockReturnValue(false);
    state.rerender({ owner: { ...state.controller, settings: { requires_restart: true } } as SettingsController });
    act(() => state.result.current.requestExit(leave));
    const previousExit = state.result.current.pendingExit;
    expect(previousExit).not.toBeNull();
    act(() => state.result.current.selectSection("memory"));
    expect(state.result.current.pendingExit).toBeNull();
    act(() => previousExit?.());
    expect(leave).not.toHaveBeenCalled();
});
