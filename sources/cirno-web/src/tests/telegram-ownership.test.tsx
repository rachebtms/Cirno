import {
  act,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { useTelegramBinding } from "@/features/telegram/model/useTelegramBinding";
import { useTelegramPairing } from "@/features/telegram/model/useTelegramPairing";
import { TelegramSettings } from "@/features/telegram/TelegramSettings";
import { PairingPin } from "@/features/telegram/ui/PairingPin";
import { copyTextToClipboard } from "@/lib/clipboard";
import type { TelegramBinding, TelegramPin } from "@/lib/contracts/telegram";
import type { WebUIMutationTransport } from "@/lib/api";
vi.mock("@/lib/clipboard", () => ({ copyTextToClipboard: vi.fn() }));
const unbound: TelegramBinding = {
  bound: false,
  enabled: true,
  notifications: ["router", "operations"],
  webui_url: "",
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function transport(
  handle: (action: string, values: Record<string, unknown>) => unknown,
) {
  const requestMutation = vi.fn(
    async <T,>(
      _method: string,
      payload: { action: string; values: Record<string, unknown> },
    ) => (await handle(payload.action, payload.values)) as T,
  );
  return {
    client: { requestMutation } as WebUIMutationTransport,
    requestMutation,
  };
}
function usePairing(client: WebUIMutationTransport) {
  const binding = useTelegramBinding(client);
  return { binding, pairing: useTelegramPairing(binding) };
}
afterEach(() => {
  vi.useRealTimers();
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "visible",
  });
});
it("does not publish a prior connection's late status over a replacement instance", async () => {
  const old = deferred<TelegramBinding>(),
    first = transport(() => old.promise),
    next = transport(() => ({
      ...unbound,
      bound: true,
      username: "new-owner",
    }));
  const { result, rerender } = renderHook(
    ({ client }) => useTelegramBinding(client),
    {
      initialProps: { client: first.client },
    },
  );
  rerender({ client: next.client });
  await waitFor(() =>
    expect(result.current.status.value?.username).toBe("new-owner"),
  );
  await act(async () => {
    old.resolve({ ...unbound, bound: true, username: "old-owner" });
  });
  expect(result.current.status.value?.username).toBe("new-owner");
});
it("does not let a pending poll undo newly acknowledged notification preferences", async () => {
  vi.useFakeTimers();
  const oldPoll = deferred<TelegramBinding>();
  let reads = 0;
  const api = transport((action) =>
    action === "telegram.pin"
      ? { pin: "12345678", expires_at: Date.now() + 20000, ttl_seconds: 20 }
      : action === "telegram.settings"
        ? { ...unbound, notifications: ["router"] }
        : ++reads === 2
          ? oldPoll.promise
          : unbound,
  );
  const { result } = renderHook(() => usePairing(api.client));
  await act(async () => {});
  await act(async () => {
    await result.current.pairing.issue();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  await act(async () => {
    await result.current.binding.update(
      { notifications: ["router"] },
      "delivery",
    );
  });
  await act(async () => {
    oldPoll.resolve(unbound);
  });
  expect(result.current.binding.status.value?.notifications).toEqual(["router"]);
});
it("serializes polls, pauses in the background, and renews an expired challenge on return", async () => {
  vi.useFakeTimers();
  const pending = deferred<TelegramBinding>();
  let reads = 0,
    pins = 0;
  const api = transport((action) =>
    action === "telegram.pin"
      ? {
          pin: `${++pins}`.padStart(8, "0"),
          expires_at: Date.now() + 1000,
          ttl_seconds: 1,
        }
      : ++reads === 2
        ? pending.promise
        : unbound,
  );
  const { result } = renderHook(() => usePairing(api.client));
  await act(async () => {});
  await act(async () => {
    await result.current.pairing.issue();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10000);
  });
  expect(reads).toBe(2);
  expect(pins).toBe(1);
  act(() => {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10000);
  });
  expect(pins).toBe(1);
  expect(reads).toBe(2);
  act(() => {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(reads).toBe(2);
  await act(async () => {
    pending.resolve(unbound);
  });
  expect(pins).toBe(2);
  expect(result.current.pairing.pin?.pin).toBe("00000002");
});

it("does not start a queued status read after the view closes", async () => {
  const pending = deferred<TelegramBinding>(),
    api = transport(() => pending.promise);
  const { result, unmount } = renderHook(() => useTelegramBinding(api.client));
  let queued!: Promise<TelegramBinding | undefined>;
  act(() => {
    queued = result.current.refresh();
  });
  unmount();
  await act(async () => {
    pending.resolve(unbound);
    await queued;
  });
  expect(api.requestMutation).toHaveBeenCalledTimes(1);
});
it("pauses after failed automatic renewal until a manual retry and stops after binding", async () => {
  vi.useFakeTimers();
  let bound = false,
    pins = 0;
  const api = transport((action) => {
    if (action === "telegram.pin") {
      if (++pins === 2) throw new Error("PIN store unavailable");
      return {
        pin: `${pins}`.padStart(8, "0"),
        expires_at: Date.now() + 1000,
        ttl_seconds: 1,
      };
    }
    return { ...unbound, bound };
  });
  const { result } = renderHook(() => usePairing(api.client));
  await act(async () => {});
  await act(async () => {
    await result.current.pairing.issue();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(result.current.pairing.operation.error).toBe("PIN store unavailable");
  const calls = api.requestMutation.mock.calls.length;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });
  expect(api.requestMutation).toHaveBeenCalledTimes(calls);
  await act(async () => {
    await result.current.pairing.issue();
  });
  bound = true;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(result.current.pairing.pin).toBeNull();
  const stopped = api.requestMutation.mock.calls.length;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });
  expect(api.requestMutation).toHaveBeenCalledTimes(stopped);
});
it("uses the server deadline instead of extending a delayed PIN response", async () => {
  const pending = deferred<TelegramPin>(),
    api = transport((action) =>
      action === "telegram.pin" ? pending.promise : unbound,
    );
  const user = userEvent.setup();
  render(<TelegramSettings client={api.client} onConfigure={vi.fn()} />);
  await user.click(await screen.findByRole("button", { name: "Generate PIN" }));
  await act(async () => {
    pending.resolve({
      pin: "12345678",
      expires_at: Date.now() - 1,
      ttl_seconds: 120,
    });
  });
  expect(await screen.findByText("PIN expired")).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Copy binding command" }),
  ).toBeDisabled();
});
it("revokes the challenge through the server when pairing is cancelled", async () => {
  const api = transport((action) =>
    action === "telegram.pin"
      ? { pin: "12345678", expires_at: Date.now() + 120000, ttl_seconds: 120 }
      : unbound,
  );
  const user = userEvent.setup();
  render(<TelegramSettings client={api.client} onConfigure={vi.fn()} />);
  await user.click(await screen.findByRole("button", { name: "Generate PIN" }));
  await user.click(await screen.findByRole("button", { name: "Cancel" }));
  await waitFor(() =>
    expect(screen.queryByLabelText("Pairing PIN")).not.toBeInTheDocument(),
  );
  expect(api.requestMutation).toHaveBeenCalledWith("instance.action", {
    action: "telegram.unbind",
    values: {},
  });
});
it("copies the complete binding command with leading zeroes and reports clipboard failure", async () => {
  const copy = vi
    .mocked(copyTextToClipboard)
    .mockResolvedValueOnce(false)
    .mockResolvedValueOnce(true);
  const user = userEvent.setup();
  render(
    <PairingPin
      pin={{
        pin: "00001234",
        expires_at: Date.now() + 120000,
        ttl_seconds: 120,
      }}
      busy={false}
      onRefresh={vi.fn()}
      onCancel={vi.fn()}
    />,
  );
  await user.click(
    screen.getByRole("button", { name: "Copy binding command" }),
  );
  expect(copy).toHaveBeenCalledWith("/bind 00001234");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Could not copy to the clipboard.",
  );
  await user.click(
    screen.getByRole("button", { name: "Copy binding command" }),
  );
  await waitFor(() =>
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
  );
});
