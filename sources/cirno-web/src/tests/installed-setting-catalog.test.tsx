import { useInstalledSettingItems } from "@/components/thread/useInstalledSettingItems";
import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";

interface Catalog { items: string[] }
const eventName = "test-installed-catalog";
const getToken = () => "fixture";
const isPayload = (value: unknown): value is Catalog =>
  value !== null && typeof value === "object" && "items" in value && Array.isArray(value.items);
const selectItems = (payload: Catalog) => payload.items;

it("does not overwrite a newer event catalog after request demand changes during a slow fetch", async () => {
  let resolve!: (payload: Catalog) => void;
  const fetchPayload = vi.fn(() => new Promise<Catalog>((finish) => { resolve = finish; }));
  const { result, rerender } = renderHook(({ count }) => useInstalledSettingItems({
    requestCount: count, getToken, eventName, fetchPayload, isPayload, selectItems,
  }), { initialProps: { count: 1 } });
  act(() => window.dispatchEvent(new CustomEvent(eventName, { detail: { items: ["new"] } })));
  rerender({ count: 2 });
  await act(async () => { resolve({ items: ["old"] }); });
  expect(result.current.items).toEqual(["new"]);
  expect(fetchPayload).toHaveBeenCalledTimes(1);
});

it("retains known items after a failed refresh and retries on the next explicit demand", async () => {
  const fetchPayload = vi.fn().mockResolvedValueOnce({ items: ["known"] })
    .mockRejectedValueOnce(new Error("catalog unavailable"))
    .mockResolvedValueOnce({ items: ["updated"] });
  const { result, rerender } = renderHook(({ count }) => useInstalledSettingItems({
    requestCount: count, getToken, eventName, fetchPayload, isPayload, selectItems,
  }), { initialProps: { count: 1 } });
  await act(async () => { });
  await act(async () => { window.dispatchEvent(new Event(eventName)); });
  expect(result.current.items).toEqual(["known"]);
  expect(result.current.error).toBe("catalog unavailable");
  rerender({ count: 2 });
  await act(async () => { });
  expect(result.current.items).toEqual(["updated"]);
  expect(result.current.error).toBe("");
});
