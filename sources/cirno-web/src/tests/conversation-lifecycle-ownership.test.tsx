import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useConversationLifecycle } from "@/app/useConversationLifecycle";

type Input = Parameters<typeof useConversationLifecycle>[0];
function pending() { let resolve!: (value: string) => void, reject!: (error: Error) => void;
  const promise = new Promise<string>((done, fail) => { resolve = done; reject = fail; }); return { promise, resolve, reject }; }
function setup() {
  const client = { onError: vi.fn(() => () => {}), attach: vi.fn(), newTemporaryChat: vi.fn() };
  const input = { workspaceState: { client, activeChatIdRef: { current: null }, setWorkspaceError: vi.fn(),
    t: (key: string) => key, loading: false, sessions: [], temporaryChatActive: false, setTemporarySessions: vi.fn(),
    activeKey: null, setDraftWorkspaceScope: vi.fn(), createChat: vi.fn().mockResolvedValue("created"), draftProjectId: null,
    ptcModeEnabled: false, pendingCreatedSessionKeyRef: { current: null }, setWorkspaceOverrides: vi.fn(), assignProject: vi.fn(),
    setPendingAutomationMessage: vi.fn(), setTemporaryChatEnabled: vi.fn(), setSessionSearchOpen: vi.fn(),
    sidebarState: { title_overrides: {} }, forkChat: vi.fn().mockResolvedValue("forked") },
    conversationState: { refreshWorkspaces: vi.fn(), activeChatId: null, activeChatRunning: false, activeWorkspaceScope: null },
    conversationProjection: { navigate: vi.fn() } };
  const view = renderHook((value: Input) => useConversationLifecycle(value), { initialProps: input as unknown as Input });
  return { ...view, input, replace: () => view.rerender({ ...input, workspaceState: { ...input.workspaceState, client: { ...client } } } as unknown as Input) };
}
for (const action of ["create", "fork", "temporary"] as const) {
  for (const result of ["success", "failure"] as const) {
    it(`ignores ${action} ${result} after the connection is replaced`, async () => {
      const view = setup(), operation = pending();
      if (action === "create") view.input.workspaceState.createChat.mockReturnValue(operation.promise);
      if (action === "fork") view.input.workspaceState.forkChat.mockReturnValue(operation.promise);
      if (action === "temporary") view.input.workspaceState.client.newTemporaryChat.mockReturnValue(operation.promise);
      let done!: Promise<string | null>;
      act(() => { done = action === "create" ? view.result.current.onCreateChat() : action === "fork" ? view.result.current.onForkChat("source", 0) : view.result.current.onCreateTemporaryChat(); });
      view.replace();
      await act(async () => { if (result === "success") operation.resolve("retired-chat"); else operation.reject(new Error("Old operation failed")); await done; });
      expect(await done).toBeNull();
      expect(view.input.conversationProjection.navigate).not.toHaveBeenCalled();
      expect(view.input.workspaceState.setWorkspaceError).not.toHaveBeenCalled();
      expect(view.input.workspaceState.setTemporarySessions).not.toHaveBeenCalled();
      expect(view.input.workspaceState.pendingCreatedSessionKeyRef.current).toBeNull();
    });
  }
}
it("preserves a successful current creation and its navigation", async () => {
  const view = setup();
  await act(async () => expect(view.result.current.onCreateChat()).resolves.toBe("created"));
  expect(view.input.workspaceState.pendingCreatedSessionKeyRef.current).toBe("websocket:created");
  expect(view.input.conversationProjection.navigate).toHaveBeenCalledExactlyOnceWith({ view: "chat", activeKey: "websocket:created", settingsSection: "overview" });
});
