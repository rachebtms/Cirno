import { expect, it, vi } from "vitest";

it("changes History API URLs without dispatching hashchange", async () => {
  const listener = vi.fn();
  window.addEventListener("hashchange", listener);
  try {
    window.history.pushState({ pane: "first" }, "", "/#/first");
    window.history.replaceState({ pane: "second" }, "", "/#/second");
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(window.location.hash).toBe("#/second");
    expect(window.history.state).toEqual({ pane: "second" });
    expect(listener).not.toHaveBeenCalled();
  } finally {
    window.removeEventListener("hashchange", listener);
  }
});

it("retains hashchange for direct fragment navigation", async () => {
  const changed = new Promise<HashChangeEvent>(resolve =>
    window.addEventListener("hashchange", resolve, { once: true }));
  window.location.hash = "#/fragment-navigation";
  expect((await changed).newURL).toBe(window.location.href);
});
