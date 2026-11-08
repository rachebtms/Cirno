import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useChannelDraft } from "@/features/channels/model/useChannelDraft";
import { useChannelActions } from "@/features/channels/model/useChannelActions";
import { useChannelIntent } from "@/features/channels/model/useChannelIntent";
import { setupLayout } from "@/features/channels/model/setupLayout";
import { useEditCompletion } from "@/features/settings/shared/useEditCompletion";
import type { ChannelSetupService } from "@/features/channels/model/setupService";
import type { ChannelSetupPresentation } from "@/channel-plugins/catalog";
import type { ChannelConfigurePayload, CirnoFeatureInfo } from "@/lib/contracts/channels";

const setup: ChannelSetupPresentation = { fields: [{ key: "token", label: "Token", secret: true }] };
const feature: CirnoFeatureInfo = {
  name: "test", display_name: "Test", type: "channel", enabled: false,
  installed: true, ready: true, status: "not_enabled", requires_restart: false,
  install_supported: true, configured_fields: ["token"],
};
const saved: ChannelConfigurePayload = { name: "test", saved: true };
function service(): ChannelSetupService {
  return {
    configure: vi.fn(async () => saved),
    validate: vi.fn(async () => ({ name: "test", status: "connected", checks: [], missing_fields: [], can_enable: true, requires_restart: false })),
    disable: vi.fn(async () => ({ features: [feature], enabled_count: 0 })),
  };
}
function deferredSave() {
  let resolve!: (value: ChannelConfigurePayload) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<ChannelConfigurePayload>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function useSetup(api: ChannelSetupService) {
  const layout = setupLayout(setup, feature), draft = useChannelDraft(api, layout.editable);
  const actions = useChannelActions(api, feature, setup, layout, draft, vi.fn(), vi.fn());
  const completion = useEditCompletion(draft.revision, draft.dirty, actions.save);
  return { draft, actions, intent: useChannelIntent(api, actions, completion) };
}

it.each(["check", "enable"] as const)("retains a %s intent until the in-flight credential save finishes", async (kind) => {
  const pending = deferredSave(), api = service();
  vi.mocked(api.configure).mockReturnValueOnce(pending.promise);
  const { result } = renderHook(() => useSetup(api));
  await act(async () => result.current.draft.change("token", "new-token"));
  expect(api.configure).toHaveBeenCalledTimes(1);
  let request: Promise<unknown>;
  act(() => {
    request = kind === "check" ? result.current.intent.check() : result.current.intent.toggle(true);
    void result.current.intent.check();
  });
  expect(api.validate).not.toHaveBeenCalled();
  expect(result.current.intent.busy).toBe(true);
  await act(async () => { pending.resolve(saved); await request; });
  expect(api.validate).toHaveBeenCalledTimes(1);
  expect(api.configure).toHaveBeenCalledTimes(kind === "check" ? 1 : 2);
  expect(result.current.intent.busy).toBe(false);
});

it("leaves an unsuccessful save visible and retries before enabling", async () => {
  const pending = deferredSave(), api = service();
  vi.mocked(api.configure).mockReturnValueOnce(pending.promise);
  const { result } = renderHook(() => useSetup(api));
  await act(async () => result.current.draft.change("token", "new-token"));
  let request: Promise<unknown>;
  act(() => { request = result.current.intent.toggle(true); });
  await act(async () => { pending.reject(new Error("Credential store unavailable")); await request; });
  expect(api.validate).not.toHaveBeenCalled();
  expect(result.current.actions.feedback?.text).toBe("Credential store unavailable");
  expect(result.current.draft.values.token).toBe("new-token");
  await act(async () => { await result.current.intent.toggle(true); });
  expect(api.validate).toHaveBeenCalledTimes(1);
  expect(api.configure).toHaveBeenCalledTimes(3);
});

it("can disable a running channel even if saving its edited credentials fails", async () => {
  const pending = deferredSave(), api = service();
  vi.mocked(api.configure).mockReturnValueOnce(pending.promise);
  const { result } = renderHook(() => useSetup(api));
  await act(async () => result.current.draft.change("token", "new-token"));
  let request: Promise<unknown>;
  act(() => { request = result.current.intent.toggle(false); });
  await act(async () => { pending.reject(new Error("Credential store unavailable")); await request; });
  expect(api.disable).toHaveBeenCalledTimes(1);
  expect(api.validate).not.toHaveBeenCalled();
  expect(result.current.draft.dirty).toBe(true);
});

it.each(["replace", "unmount"] as const)("does not enable the old channel after its owner is %s", async (change) => {
  const pending = deferredSave(), first = service(), second = service();
  vi.mocked(first.configure).mockReturnValueOnce(pending.promise);
  const { result, rerender, unmount } = renderHook(({ api }) => useSetup(api), { initialProps: { api: first } });
  await act(async () => result.current.draft.change("token", "old-token"));
  let request: Promise<unknown>;
  act(() => { request = result.current.intent.toggle(true); });
  if (change === "replace") rerender({ api: second });
  else unmount();
  await act(async () => { pending.resolve(saved); await request; });
  expect(first.validate).not.toHaveBeenCalled();
  expect(first.configure).toHaveBeenCalledTimes(1);
  expect(second.configure).not.toHaveBeenCalled();
});
