import { act, renderHook } from "@testing-library/react";
import { expect, it } from "vitest";
import { useBrowserLocation } from "@/features/browser/model/useBrowserLocation";
it("normalizes an address and preserves the loaded page when a later address is rejected", () => {
  const { result } = renderHook(useBrowserLocation);
  act(() => result.current.setAddress("example.com/research"));
  act(() => result.current.navigate());
  expect(result.current.url).toBe("https://example.com/research");
  for (const address of ["https://", `${location.origin}/settings`, "file:///etc/passwd"]) {
    act(() => result.current.setAddress(address)); act(() => result.current.navigate());
    expect(result.current.error).not.toBe("");
    expect(result.current.url).toBe("https://example.com/research");
  }
});
