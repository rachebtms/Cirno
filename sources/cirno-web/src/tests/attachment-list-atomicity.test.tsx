import { act, cleanup, renderHook } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { LocalAttachment } from "../../packages/client-events/attachments";
import { useAttachedImages } from "@/hooks/useAttachedImages";
import { encodeImage } from "@/lib/imageEncode";

vi.mock("@/lib/imageEncode", () => ({ encodeImage: vi.fn() }));
const NativeURL = URL;
beforeEach(() => {
  vi.mocked(encodeImage).mockReset().mockResolvedValue({ id: "fake", ok: true, dataUrl: "data:image/png;base64,eA==", bytes: 1, normalized: false });
  vi.stubGlobal("URL", class extends NativeURL {
    static createObjectURL = vi.fn(() => "blob:fixture");
    static revokeObjectURL = vi.fn();
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function file(name: string): LocalAttachment {
  return { path: "/workspace/" + name, name, size: 1, mime: "text/plain", kind: "file", url: "" };
}

it("clears the latest queued additions before another addition", () => {
  const hook = renderHook(() => useAttachedImages());
  act(() => { hook.result.current.addLocal(file("old")); });
  act(() => {
    hook.result.current.addLocal(file("queued"));
    hook.result.current.clear();
    hook.result.current.addLocal(file("new"));
  });
  expect(hook.result.current.images.map(image => image.file.name)).toEqual(["new"]);
});

it("returns the next focus immediately for successive deletions", () => {
  const hook = renderHook(() => useAttachedImages());
  act(() => { for (const name of ["a", "b", "c"]) hook.result.current.addLocal(file(name)); });
  const [a, b, c] = hook.result.current.images;
  act(() => {
    expect(hook.result.current.remove(b.id).nextFocusId).toBe(c.id);
    expect(hook.result.current.remove(a.id).nextFocusId).toBe(c.id);
  });
  expect(hook.result.current.images.map(image => image.file.name)).toEqual(["c"]);
});

it("does not resurrect a removed attachment when adding in the same batch", () => {
  const hook = renderHook(() => useAttachedImages());
  act(() => { for (const name of ["a", "b", "c"]) hook.result.current.addLocal(file(name)); });
  const [a, b] = hook.result.current.images;
  act(() => {
    hook.result.current.remove(b.id);
    hook.result.current.remove(a.id);
    hook.result.current.addLocal(file("new"));
  });
  expect(hook.result.current.images.map(image => image.file.name)).toEqual(["c", "new"]);
});

it("keeps the restored draft when a new attachment follows restoration", () => {
  const hook = renderHook(() => useAttachedImages());
  act(() => {
    hook.result.current.addLocal(file("temporary"));
    hook.result.current.restoreReadyImages([{ local: file("restored") }]);
    hook.result.current.addLocal(file("new"));
  });
  expect(hook.result.current.images.map(image => image.file.name)).toEqual(["restored", "new"]);
});

it("does not start queued encoding for an attachment that was cleared", async () => {
  const hook = renderHook(() => useAttachedImages());
  await act(async () => {
    hook.result.current.enqueue([new File(["x"], "preview.png", { type: "image/png" })]);
    hook.result.current.clear();
    await Promise.resolve();
  });
  expect(hook.result.current.images).toEqual([]);
  expect(encodeImage).not.toHaveBeenCalled();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fixture");
});

it("still completes encoding for a retained attachment", async () => {
  const hook = renderHook(() => useAttachedImages());
  await act(async () => {
    hook.result.current.enqueue([new File(["x"], "preview.png", { type: "image/png" })]);
    await Promise.resolve();
  });
  expect(encodeImage).toHaveBeenCalledTimes(1);
  expect(hook.result.current.images[0].status).toBe("ready");
  expect(hook.result.current.encoding).toBe(false);
});

it("does not start queued encoding after the composer unmounts", async () => {
  const hook = renderHook(() => useAttachedImages());
  await act(async () => {
    hook.result.current.enqueue([new File(["x"], "preview.png", { type: "image/png" })]);
    hook.unmount();
    await Promise.resolve();
  });
  expect(encodeImage).not.toHaveBeenCalled();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fixture");
});

it("keeps a live composer active through StrictMode effect replay", async () => {
  const hook = renderHook(() => useAttachedImages(), { wrapper: ({ children }) => <StrictMode>{children}</StrictMode> });
  await act(async () => {
    hook.result.current.enqueue([new File(["x"], "preview.png", { type: "image/png" })]);
    await Promise.resolve();
  });
  expect(encodeImage).toHaveBeenCalledTimes(1);
  expect(hook.result.current.images[0].status).toBe("ready");
});
