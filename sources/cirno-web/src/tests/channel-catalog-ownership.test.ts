import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useChannelSelection } from "@/features/channels/model/useChannelSelection";
import { useChannelCatalog } from "@/features/channels/model/useChannelCatalog";
import i18n from "@/i18n";
import type { CirnoFeaturesPayload } from "@/lib/contracts/channels";
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
it("serializes close requests and retains selection until draft completion acknowledges", async () => {
  const owner = {},
    pending = deferred<boolean>(),
    save = vi.fn(() => pending.promise),
    register = vi.fn();
  const { result } = renderHook(() => useChannelSelection(owner, register));
  act(() => result.current.select("telegram"));
  act(() => result.current.setCompletion(save));
  act(() => {
    void result.current.close();
    void result.current.close();
  });
  expect(save).toHaveBeenCalledTimes(1);
  expect(result.current.selected?.name).toBe("telegram");
  await act(async () => pending.resolve(false));
  expect(result.current.selected?.name).toBe("telegram");
  act(() => result.current.setCompletion(async () => true));
  await act(async () => {
    await result.current.close();
  });
  expect(result.current.selected).toBeNull();
  expect(register).toHaveBeenLastCalledWith(null);
});
it("surfaces a rejected draft completion and permits a subsequent close", async () => {
  const owner = {};
  const { result } = renderHook(() => useChannelSelection(owner));
  act(() => result.current.select("telegram"));
  act(() =>
    result.current.setCompletion(async () => {
      throw new Error("Channel draft write failed");
    }),
  );
  await act(async () => {
    await result.current.close();
  });
  expect(result.current.mutation.error).toBe("Channel draft write failed");
  expect(result.current.selected?.name).toBe("telegram");
  act(() => result.current.setCompletion(null));
  await act(async () => {
    await result.current.close();
  });
  expect(result.current.selected).toBeNull();
});
it("does not close a replacement connection from an earlier connection's acknowledgement", async () => {
  const pending = deferred<boolean>(),
    first = {},
    next = {};
  const { result, rerender } = renderHook(
    ({ owner }) => useChannelSelection(owner),
    { initialProps: { owner: first } },
  );
  act(() => result.current.select("telegram"));
  act(() => result.current.setCompletion(() => pending.promise));
  act(() => {
    void result.current.close();
  });
  rerender({ owner: next });
  expect(result.current.selected).toBeNull();
  act(() => result.current.select("websocket"));
  await act(async () => pending.resolve(true));
  expect(result.current.selected?.name).toBe("websocket");
});
it("freezes the initial filter across activation and resets it for a new connection", async () => {
  const owner = {},
    next = {};
  const payload: CirnoFeaturesPayload = {
    features: [
      {
        name: "telegram",
        display_name: "Telegram",
        type: "channel",
        enabled: false,
        installed: true,
        ready: true,
        status: "not_enabled",
        install_supported: true,
        requires_restart: false,
      },
    ],
    enabled_count: 0,
  };
  const { result, rerender } = renderHook(
    ({ owner, payload }) => useChannelCatalog(owner, payload, i18n.t),
    { initialProps: { owner, payload } },
  );
  await waitFor(() => expect(result.current.filter).toBe("all"));
  act(() => result.current.changeQuery("tele"));
  const enabled = {
    ...payload,
    features: payload.features.map((feature) => ({
      ...feature,
      enabled: true,
    })),
    enabled_count: 1,
  };
  rerender({ owner, payload: enabled });
  expect(result.current.filter).toBe("all");
  expect(result.current.query).toBe("tele");
  rerender({ owner: next, payload: enabled });
  expect(result.current.query).toBe("");
  await waitFor(() => expect(result.current.filter).toBe("enabled"));
});
