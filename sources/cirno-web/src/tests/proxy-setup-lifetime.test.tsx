import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SharedProxySetupDialog } from "@/features/settings/shared/SharedProxySetupDialog";
import { useProxySetup } from "@/features/settings/shared/useProxySetup";
import type { CirnoClient } from "@/lib/cirno-client";

function deferred() {
  let resolve!: () => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<void>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("admits one proxy save before React renders its pending state", async () => {
  const pending = deferred(), save = vi.fn(() => pending.promise), close = vi.fn();
  const { result } = renderHook(() => useProxySetup(save, close, false));
  act(() => result.current.change("http://proxy.example:8080"));
  const submit = result.current.save;
  let first!: Promise<unknown>, second!: Promise<unknown>;
  act(() => { first = submit(); second = submit(); });
  await act(async () => { pending.resolve(); await Promise.all([first, second]); });
  expect(save).toHaveBeenCalledTimes(1);
  expect(close).toHaveBeenCalledTimes(1);
});

it("ignores a retained submit callback after the setup has unmounted", async () => {
  const save = vi.fn(async () => {}), close = vi.fn();
  const { result, unmount } = renderHook(() => useProxySetup(save, close, false));
  act(() => result.current.change("http://proxy.example:8080"));
  const submit = result.current.save;
  unmount();
  await submit();
  expect(save).not.toHaveBeenCalled();
  expect(close).not.toHaveBeenCalled();
});

it("does not close a replacement setup when an unmounted save succeeds", async () => {
  const pending = deferred(), close = vi.fn();
  const { result, unmount } = renderHook(() => useProxySetup(() => pending.promise, close, false));
  act(() => result.current.change("http://proxy.example:8080"));
  let operation!: Promise<unknown>;
  act(() => { operation = result.current.save(); });
  unmount();
  await act(async () => { pending.resolve(); await operation; });
  expect(close).not.toHaveBeenCalled();
});

it("keeps a failed proxy draft for an explicit retry", async () => {
  const save = vi.fn().mockRejectedValueOnce(new Error("Proxy was rejected")).mockResolvedValueOnce(undefined);
  const close = vi.fn();
  const { result } = renderHook(() => useProxySetup(save, close, false));
  act(() => result.current.change("http://proxy.example:8080"));
  await act(async () => { await result.current.save(); });
  expect(result.current.error).toBe("Proxy was rejected");
  expect(result.current.address).toBe("http://proxy.example:8080");
  expect(result.current.pending).toBe(false);
  await act(async () => { await result.current.save(); });
  expect(save).toHaveBeenCalledTimes(2);
  expect(close).toHaveBeenCalledTimes(1);
});

it("clears a credential-bearing proxy draft when the gateway client changes", async () => {
  const first = {} as CirnoClient, second = {} as CirnoClient;
  const save = vi.fn(async () => {}), close = vi.fn();
  const { rerender } = render(<SharedProxySetupDialog client={first} onSave={save} onClose={close} busy={false} />);
  const input = await screen.findByRole("textbox", { name: "Shared proxy" });
  fireEvent.change(input, { target: { value: "http://old-proxy.example:8080" } });
  fireEvent.click(screen.getByRole("button", { name: "Authentication (optional)" }));
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: "old-owner" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "old-secret" } });
  rerender(<SharedProxySetupDialog client={second} onSave={save} onClose={close} busy={false} />);
  await waitFor(() => expect(screen.getByRole("textbox", { name: "Shared proxy" })).toHaveValue(""));
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  expect(screen.queryByDisplayValue("old-secret")).not.toBeInTheDocument();
  expect(save).not.toHaveBeenCalled();
});

it("keeps the new gateway save pending when the old gateway save settles", async () => {
  const first = {} as CirnoClient, second = {} as CirnoClient;
  const oldSave = deferred(), newSave = deferred(), close = vi.fn();
  const saveFirst = vi.fn(() => oldSave.promise), saveSecond = vi.fn(() => newSave.promise);
  const { rerender } = render(<SharedProxySetupDialog client={first} onSave={saveFirst} onClose={close} busy={false} />);
  fireEvent.change(await screen.findByRole("textbox", { name: "Shared proxy" }), { target: { value: "http://old.example:8080" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(saveFirst).toHaveBeenCalledTimes(1));
  rerender(<SharedProxySetupDialog client={second} onSave={saveSecond} onClose={close} busy={false} />);
  const input = await screen.findByRole("textbox", { name: "Shared proxy" });
  expect(input).toBeEnabled();
  fireEvent.change(input, { target: { value: "http://new.example:8080" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(saveSecond).toHaveBeenCalledWith("http://new.example:8080"));
  await act(async () => { oldSave.resolve(); });
  expect(close).not.toHaveBeenCalled();
  expect(input).toBeDisabled();
  expect(input).toHaveValue("http://new.example:8080");
  await act(async () => { newSave.resolve(); });
  await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
});
