import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";
import { useChannelInstances } from "@/features/channels/model/useChannelInstances";
import type {
  CirnoFeatureInfo,
  CirnoFeaturesPayload,
  CirnoChannelInstanceInfo,
} from "@/lib/contracts/channels";
const instance: CirnoChannelInstanceInfo = {
  id: "worker",
  name: "Worker",
  enabled: true,
  configured: true,
  config_values: {},
  configured_fields: [],
  runtime_status: "running",
};
const feature: CirnoFeatureInfo = {
  name: "cluster",
  display_name: "Cluster",
  type: "channel",
  enabled: true,
  installed: true,
  ready: true,
  status: "enabled",
  install_supported: true,
  requires_restart: false,
  instances: [instance],
};
const payload: CirnoFeaturesPayload = { features: [feature], enabled_count: 1 };
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function harness(
  handler: (action: string, values: Record<string, unknown>) => unknown,
) {
  const requestMutation = vi.fn(
      async (action: string, values: Record<string, unknown>) =>
        handler(action, values),
    ),
    client = { requestMutation } as unknown as CirnoClient,
    onUpdate = vi.fn();
  const hook = renderHook(() => useChannelInstances(feature, onUpdate), {
    wrapper: ({ children }) => (
      <ClientProvider client={client} token="fixture">
        {children}
      </ClientProvider>
    ),
  });
  return { ...hook, requestMutation, onUpdate };
}
it("serializes operations across instances and retains the selected operation's target", async () => {
  const pending = deferred<CirnoFeaturesPayload>(),
    view = harness(() => pending.promise);
  act(() => {
    void view.result.current.toggle(instance, false);
    void view.result.current.toggle({ ...instance, id: "second" }, true);
  });
  expect(view.requestMutation).toHaveBeenCalledTimes(1);
  expect(view.requestMutation).toHaveBeenCalledWith(
    "settings.feature.disable",
    { name: "cluster", instance_id: "worker" },
    expect.any(Number),
  );
  expect(view.result.current.operation?.id).toBe("worker");
  await act(async () => pending.resolve(payload));
  expect(view.onUpdate).toHaveBeenCalledWith(payload);
  expect(view.result.current.operation).toBeNull();
});
it("targets credential deletion to the selected instance and preserves its enabled state", async () => {
  const view = harness(() => ({
    name: "cluster",
    saved: true,
    cirno_features: payload,
  }));
  await act(async () => {
    await view.result.current.save(
      { ...instance, id: "second", enabled: false },
      { token: null },
    );
  });
  expect(view.requestMutation).toHaveBeenCalledWith(
    "settings.channel.configure",
    {
      name: "cluster",
      values: { token: null },
      enable: false,
      instance_id: "second",
    },
    expect.any(Number),
  );
  expect(view.onUpdate).toHaveBeenCalledWith(payload);
});
it("settles a pending instance operation without updating an unmounted panel", async () => {
  const pending = deferred<CirnoFeaturesPayload>(),
    view = harness(() => pending.promise);
  act(() => {
    void view.result.current.toggle(instance, false);
  });
  view.unmount();
  await act(async () => pending.resolve(payload));
  expect(view.onUpdate).not.toHaveBeenCalled();
});
