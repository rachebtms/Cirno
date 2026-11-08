import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useChannelDraft } from "@/features/channels/model/useChannelDraft";
import { useChannelActions } from "@/features/channels/model/useChannelActions";
import { setupLayout } from "@/features/channels/model/setupLayout";
import { channelValuesForSubmit } from "@/features/channels/model/fieldValues";
import type { ChannelSetupService } from "@/features/channels/model/setupService";
import type { ChannelSetupPresentation } from "@/channel-plugins/catalog";
import type {
  ChannelConfigurePayload,
  ChannelValidationPayload,
  CirnoFeatureInfo,
} from "@/lib/contracts/channels";
const setup: ChannelSetupPresentation = {
  fields: [
    { key: "host", label: "Host" },
    { key: "token", label: "Token", secret: true },
  ],
  requirements: [{ alternatives: [["token"]] }],
};
const feature: CirnoFeatureInfo = {
  name: "test",
  display_name: "Test channel",
  type: "channel",
  enabled: false,
  installed: true,
  ready: true,
  status: "not_enabled",
  requires_restart: false,
  install_supported: true,
  configured_fields: ["token"],
};
const valid: ChannelValidationPayload = {
  name: "test",
  status: "connected",
  checks: [],
  missing_fields: [],
  can_enable: true,
  requires_restart: false,
};
const saved: ChannelConfigurePayload = {
  name: "test",
  saved: true,
  cirno_features: { features: [feature], enabled_count: 0 },
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function service(
  patch: Partial<ChannelSetupService> = {},
): ChannelSetupService {
  return {
    configure: vi.fn(async () => saved),
    validate: vi.fn(async () => valid),
    disable: vi.fn(async () => ({ features: [feature], enabled_count: 0 })),
    ...patch,
  };
}
function useSetup(api: ChannelSetupService, onUpdate = vi.fn()) {
  const layout = setupLayout(setup, feature),
    draft = useChannelDraft(api, layout.editable, { host: "saved.example" });
  const actions = useChannelActions(
    api,
    feature,
    setup,
    layout,
    draft,
    onUpdate,
    vi.fn(),
  );
  return { draft, actions };
}
it("sends changed fields only so an old catalog cannot overwrite untouched settings", () => {
  expect(
    channelValuesForSubmit(
      setup.fields!,
      { host: "old.example", token: "new-token" },
      new Set(["token"]),
    ),
  ).toEqual({ token: "new-token" });
});
it("acknowledges only the submitted snapshot while retaining edits made during its save", async () => {
  const pending = deferred<ChannelConfigurePayload>(),
    api = service({ configure: vi.fn(() => pending.promise) });
  const { result } = renderHook(() => useSetup(api));
  act(() => {
    result.current.draft.change("host", "first.example");
    result.current.draft.change("token", "first-token");
  });
  let saving: Promise<boolean>;
  act(() => {
    saving = result.current.actions.save();
  });
  expect(api.configure).toHaveBeenCalledWith({
    host: "first.example",
    token: "first-token",
  });
  act(() => result.current.draft.change("host", "later.example"));
  await act(async () => {
    pending.resolve(saved);
    await saving!;
  });
  expect(result.current.draft.values.host).toBe("later.example");
  expect(result.current.draft.payload).toEqual({ host: "later.example" });
  expect(result.current.draft.dirty).toBe(true);
});
it("serializes draft saves and manual checks, then allows retry after a failed write", async () => {
  let fail!: (reason: Error) => void;
  const pending = new Promise<ChannelConfigurePayload>((_, reject) => {
    fail = reject;
  });
  const api = service({
    configure: vi
      .fn()
      .mockReturnValueOnce(pending)
      .mockResolvedValueOnce(saved),
  });
  const { result } = renderHook(() => useSetup(api));
  act(() => result.current.draft.change("host", "draft.example"));
  act(() => {
    void result.current.actions.save();
    void result.current.actions.save();
    void result.current.actions.check();
  });
  expect(api.configure).toHaveBeenCalledTimes(1);
  expect(api.validate).not.toHaveBeenCalled();
  await act(async () => fail(new Error("Channel store unavailable")));
  expect(result.current.actions.feedback?.text).toBe(
    "Channel store unavailable",
  );
  expect(result.current.draft.values.host).toBe("draft.example");
  await act(async () => {
    await result.current.actions.save();
  });
  expect(api.configure).toHaveBeenCalledTimes(2);
  expect(result.current.draft.dirty).toBe(false);
});
it("does not write after validation resolves for a connection which has been replaced", async () => {
  const pending = deferred<ChannelValidationPayload>(),
    first = service({ validate: vi.fn(() => pending.promise) }),
    second = service(),
    update = vi.fn();
  const { result, rerender } = renderHook(({ api }) => useSetup(api, update), {
    initialProps: { api: first },
  });
  act(() => {
    void result.current.actions.toggle(true);
  });
  expect(first.validate).toHaveBeenCalledTimes(1);
  rerender({ api: second });
  await act(async () => pending.resolve(valid));
  expect(first.configure).not.toHaveBeenCalled();
  expect(update).not.toHaveBeenCalled();
  expect(result.current.actions.feedback).toBeNull();
});
it("does not publish a completed write or its errors into another connection", async () => {
  const pending = deferred<ChannelConfigurePayload>(),
    first = service({ configure: vi.fn(() => pending.promise) }),
    second = service(),
    update = vi.fn();
  const { result, rerender } = renderHook(({ api }) => useSetup(api, update), {
    initialProps: { api: first },
  });
  act(() => result.current.draft.change("token", "old-instance-token"));
  act(() => {
    void result.current.actions.save();
  });
  rerender({ api: second });
  expect(result.current.draft.values.token).toBe("");
  act(() => result.current.draft.change("host", "new-instance.example"));
  await act(async () => pending.resolve(saved));
  expect(update).not.toHaveBeenCalled();
  expect(result.current.draft.values.host).toBe("new-instance.example");
  expect(result.current.actions.feedback).toBeNull();
});
it("does not launch a queued draft save after its view is unmounted", async () => {
  const api = service(),
    { result, unmount } = renderHook(() => useSetup(api));
  act(() => result.current.draft.change("token", "unsent-token"));
  const save = result.current.actions.save;
  unmount();
  expect(await save()).toBe(false);
  expect(api.configure).not.toHaveBeenCalled();
});
it("retries a rejected server validation without committing its invalid credentials", async () => {
  const invalid = {
    ...valid,
    status: "invalid",
    can_enable: false,
    missing_fields: ["token"],
    message: "Token rejected",
  };
  const api = service({
    validate: vi
      .fn()
      .mockResolvedValueOnce(invalid)
      .mockResolvedValueOnce(valid),
  });
  const { result } = renderHook(() => useSetup(api));
  act(() => result.current.draft.change("token", "new-token"));
  await act(async () => {
    await result.current.actions.toggle(true);
  });
  expect(api.configure).not.toHaveBeenCalled();
  expect(result.current.actions.errors.token).toBeTruthy();
  expect(result.current.draft.dirty).toBe(true);
  await act(async () => {
    await result.current.actions.toggle(true);
  });
  expect(api.configure).toHaveBeenCalledWith({ token: "new-token" }, true);
  expect(result.current.draft.dirty).toBe(false);
});
