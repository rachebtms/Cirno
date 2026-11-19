import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useRequest } from "@/ui/resources/useRequest";
import { useMutation } from "@/ui/resources/useMutation";
import { useLifetime } from "@/ui/resources/useLifetime";
import { useResourceScope } from "@/ui/resources/useResourceScope";
import { useScopedState } from "@/ui/resources/useScopedState";
import { createElement, startTransition, StrictMode, Suspense, type ReactNode } from "react";
import { flushSync } from "react-dom";

afterEach(cleanup);

it("keeps the committed owner usable while a replacement render is suspended and abandoned", () => {
  const pending = new Promise<void>(() => {});
  let replacements = 0;
  const { result, rerender } = renderHook(({ owner, suspended }) => {
    const current = useLifetime(owner);
    if (suspended) { replacements += 1; throw pending; }
    return current;
  }, {
    initialProps: { owner: "first", suspended: false },
    wrapper: ({ children }: { children: ReactNode }) => createElement(Suspense, { fallback: null }, children),
  });
  const first = result.current;
  act(() => startTransition(() => rerender({ owner: "second", suspended: true })));
  expect(replacements).toBeGreaterThan(0);
  expect(first()).toBe(true);
  rerender({ owner: "first", suspended: false });
  expect(result.current).toBe(first);
  expect(first()).toBe(true);
});

it("settles an accepted write when Suspense temporarily hides the same mounted owner", async () => {
  const hidden = new Promise<void>(() => {});
  let finish!: (value: string) => void;
  const ack = vi.fn();
  const { result, rerender } = renderHook(({ suspended }) => {
    const mutation = useMutation("owner");
    if (suspended) throw hidden;
    return mutation;
  }, {
    initialProps: { suspended: false },
    wrapper: ({ children }: { children: ReactNode }) => createElement(Suspense, { fallback: null }, children),
  });
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.run(() => new Promise<string>((resolve) => { finish = resolve; }), ack);
  });
  rerender({ suspended: true });
  await act(async () => { finish("saved"); await pending; });
  rerender({ suspended: false });
  expect(ack).toHaveBeenCalledExactlyOnceWith("saved");
  expect(result.current.busy).toBe(false);
});

it("lets the latest read win and invalidates outstanding reads on assign or clear", async () => {
  const { result } = renderHook(() => useRequest<string>("owner"));
  let finish!: (value: string) => void;
  const startPending = () => result.current.load(
    () => new Promise<string>((resolve) => { finish = resolve; }),
  );
  let pending!: Promise<unknown>;
  act(() => { pending = startPending(); });
  await act(() => result.current.load(async () => "latest"));
  await act(async () => { finish("old"); await pending; });
  expect(result.current.value).toBe("latest");
  act(() => { pending = startPending(); result.current.assign("assigned"); });
  await act(async () => { finish("replaced"); await pending; });
  expect(result.current.value).toBe("assigned");
  act(() => { pending = startPending(); result.current.clear(); });
  await act(async () => { finish("cleared"); await pending; });
  expect(result.current.status).toBe("idle");
  expect(result.current.value).toBeNull();
});

it("allows only one pending write per scope and preserves it when clearing errors", async () => {
  const { result } = renderHook(() => useMutation("owner"));
  let finish!: (value: string) => void;
  const ack = vi.fn();
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.run(
      () => new Promise<string>((resolve) => { finish = resolve; }), ack,
    );
    result.current.clear();
  });
  const duplicate = vi.fn(async () => "duplicate");
  await act(() => result.current.run(duplicate, ack));
  expect(duplicate).not.toHaveBeenCalled();
  expect(result.current.busy).toBe(true);
  await act(async () => { finish("saved"); await pending; });
  expect(ack).toHaveBeenCalledExactlyOnceWith("saved");
  expect(result.current.busy).toBe(false);
});

it("resets scoped state immediately and cannot revive a retained setter on return", () => {
  const { result, rerender, unmount } = renderHook((owner: string) => {
    const scope = useResourceScope(owner);
    const [state, setState] = useScopedState(scope, () => ({ owner, count: 0 }));
    return { state, setState };
  }, { initialProps: "first" });
  const staleSetter = result.current.setState;
  act(() => staleSetter((state) => ({ ...state, count: 7 })));
  rerender("second");
  expect(result.current.state).toEqual({ owner: "second", count: 0 });
  rerender("first");
  act(() => staleSetter((state) => ({ ...state, count: 99 })));
  expect(result.current.state).toEqual({ owner: "first", count: 0 });
  const update = vi.fn((state) => state);
  const setter = result.current.setState;
  unmount();
  act(() => setter(update));
  expect(update).not.toHaveBeenCalled();
});

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

it("does not revive retained callbacks when the exact same owner returns", () => {
  const firstOwner = {}, secondOwner = {};
  const { result, rerender } = renderHook(useLifetime, { initialProps: firstOwner });
  const first = result.current;
  rerender(secondOwner);
  rerender(firstOwner);
  expect(first()).toBe(false);
  expect(result.current()).toBe(true);
});

it("does not revive an old busy state after returning to its owner", async () => {
  let finish!: (value: string) => void;
  const ack = vi.fn();
  const { result, rerender } = renderHook(useMutation, { initialProps: "first" });
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.run(() => new Promise(resolve => { finish = resolve; }), ack);
  });
  const staleRun = result.current.run;
  rerender("second");
  rerender("first");
  expect(result.current.busy).toBe(false);
  const write = vi.fn(async () => "must not run");
  await staleRun(write, ack);
  expect(write).not.toHaveBeenCalled();
  await act(async () => { finish("old"); await pending; });
  expect(ack).not.toHaveBeenCalled();
});

it("does not revive an old read snapshot or its retained loader", async () => {
  const { result, rerender } = renderHook(useRequest<string>, { initialProps: "first" });
  await act(() => result.current.load(async () => "old"));
  const staleLoad = result.current.load;
  rerender("second");
  rerender("first");
  expect(result.current.value).toBeNull();
  const read = vi.fn(async () => "must not load");
  await staleLoad(read);
  expect(read).not.toHaveBeenCalled();
  await act(() => result.current.load(async () => "new"));
  expect(result.current.value).toBe("new");
});

it("keeps a same-owner callback stable and current through StrictMode replay", () => {
  const owner = {};
  const { result, rerender, unmount } = renderHook(useLifetime, {
    initialProps: owner,
    wrapper: ({ children }: { children: ReactNode }) => createElement(StrictMode, null, children),
  });
  const current = result.current;
  expect(current()).toBe(true);
  rerender(owner);
  expect(result.current).toBe(current);
  expect(current()).toBe(true);
  unmount();
  expect(current()).toBe(false);
});

it("does not overwrite a new owner's busy state after an acknowledgement switches views", async () => {
  let finish!: (value: string) => void;
  const { result, rerender } = renderHook(useMutation, { initialProps: "first" });
  let second!: Promise<unknown>;
  await act(async () => {
    await result.current.run(async () => "first result", () => {
      flushSync(() => rerender("second"));
      second = result.current.run(() => new Promise(resolve => { finish = resolve; }), vi.fn());
    });
  });
  expect(result.current.busy).toBe(true);
  await act(async () => { finish("second result"); await second; });
  expect(result.current.busy).toBe(false);
});
