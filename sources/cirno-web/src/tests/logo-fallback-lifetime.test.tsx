import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it } from "vitest";
import { __clearLogoFallbackCacheForTests, useLogoFallback } from "@/hooks/useLogoFallback";

const a = ["/a-primary.svg", "/a-backup.svg"];
const b = ["/b-primary.svg", "/b-backup.svg"];

beforeEach(__clearLogoFallbackCacheForTests);
afterEach(cleanup);

it("uses the new catalog entry's first image from its first render", () => {
  const frames: Array<string | undefined> = [];
  const hook = renderHook(({ urls }) => {
    const image = useLogoFallback(urls);
    frames.push(image.logoUrl);
    return image;
  }, { initialProps: { urls: a } });
  act(() => hook.result.current.onLogoError());
  expect(hook.result.current.logoUrl).toBe(a[1]);
  frames.length = 0;
  hook.rerender({ urls: b });
  expect(frames[0]).toBe(b[0]);
});

it("ignores an old entry's error after the next entry is visible", () => {
  const hook = renderHook(({ urls }) => useLogoFallback(urls), { initialProps: { urls: a } });
  const old = hook.result.current;
  hook.rerender({ urls: b });
  act(() => old.onLogoError());
  expect(hook.result.current.logoUrl).toBe(b[0]);
});

it("does not revive old handlers after switching away and back", () => {
  const hook = renderHook(({ urls }) => useLogoFallback(urls), { initialProps: { urls: a } });
  const old = hook.result.current;
  hook.rerender({ urls: b });
  hook.rerender({ urls: a });
  act(() => old.onLogoError());
  expect(hook.result.current.logoUrl).toBe(a[0]);
});

it("ignores a retired image's load after moving to a fallback", () => {
  const hook = renderHook(() => useLogoFallback(a));
  const old = hook.result.current;
  act(() => old.onLogoError());
  act(() => old.onLogoLoad());
  hook.unmount();
  const next = renderHook(() => useLogoFallback(a));
  expect(next.result.current.logoUrl).toBe(a[1]);
  expect(next.result.current.logoLoaded).toBe(false);
});

it("does not poison shared failure state after unmount", () => {
  const hook = renderHook(() => useLogoFallback(a));
  const old = hook.result.current;
  hook.unmount();
  act(() => old.onLogoError());
  const next = renderHook(() => useLogoFallback(a));
  expect(next.result.current.logoUrl).toBe(a[0]);
});

it("retains a loaded fallback across equivalent URL lists", () => {
  const hook = renderHook(({ urls }) => useLogoFallback(urls), { initialProps: { urls: a } });
  act(() => hook.result.current.onLogoError());
  act(() => hook.result.current.onLogoLoad());
  hook.rerender({ urls: [...a] });
  expect(hook.result.current.logoUrl).toBe(a[1]);
  expect(hook.result.current.logoLoaded).toBe(true);
});
