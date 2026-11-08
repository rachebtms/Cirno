import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useRequest } from "@/ui/resources/useRequest";
import { useMutation } from "@/ui/resources/useMutation";
import { useLifetime } from "@/ui/resources/useLifetime";

afterEach(cleanup);

it("invalidates callbacks immediately on owner replacement and after unmount", () => {
  const { result, rerender, unmount } = renderHook(useLifetime, { initialProps: "first" });
  const first = result.current;
  expect(first()).toBe(true);
  rerender("second");
  expect(first()).toBe(false);
  expect(result.current()).toBe(true);
  unmount();
  expect(result.current()).toBe(false);
});

it("does not start writes through a retained callback after unmount", async () => {
  const { result, unmount } = renderHook(useMutation, { initialProps: "owner" });
  const run = result.current.run;
  const write = vi.fn().mockResolvedValue("done"),
    ack = vi.fn();
  unmount();
  await run(write, ack);
  expect(write).not.toHaveBeenCalled();
  expect(ack).not.toHaveBeenCalled();
});

it("ignores an old write acknowledgement while allowing the new owner to write", async () => {
  let finish!: (value: string) => void;
  const ack = vi.fn();
  const { result, rerender } = renderHook(useMutation, { initialProps: "first" });
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.run(
      () =>
        new Promise<string>((resolve) => {
          finish = resolve;
        }),
      ack,
    );
  });
  rerender("second");
  await act(() => result.current.run(async () => "current", ack));
  await act(async () => {
    finish("old");
    await pending;
  });
  expect(ack).toHaveBeenCalledExactlyOnceWith("current");
  expect(result.current.busy).toBe(false);
});

it("keeps request data scoped to the current mounted owner", async () => {
  let finish!: (value: string) => void;
  const { result, rerender, unmount } = renderHook(useRequest<string>, { initialProps: "first" });
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.load(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
  });
  rerender("second");
  await act(() => result.current.load(async () => "current"));
  await act(async () => {
    finish("old");
    await pending;
  });
  expect(result.current.value).toBe("current");
  const load = result.current.load,
    request = vi.fn();
  unmount();
  await load(request);
  expect(request).not.toHaveBeenCalled();
});
