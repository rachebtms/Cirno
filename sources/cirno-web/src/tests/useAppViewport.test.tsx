import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAppViewport } from "@/hooks/useAppViewport";

let touch = true;
vi.mock("@/hooks/useMediaQuery", () => ({ useMediaQuery: () => touch }));

function AppSurface() {
  useAppViewport();
  return <><header>Navigation</header><textarea aria-label="Draft" defaultValue="中文草稿" /></>;
}

describe("app visual viewport", () => {
  let root: HTMLDivElement;
  let viewport: EventTarget & { height: number; offsetTop: number; scale: number };
  beforeEach(() => {
    touch = true;
    vi.stubGlobal("innerHeight", 746);
    vi.stubGlobal("innerWidth", 390);
    root = document.createElement("div");
    root.id = "root";
    document.body.append(root);
    viewport = Object.assign(new EventTarget(), { height: 746, offsetTop: 0, scale: 1 });
    vi.stubGlobal("visualViewport", viewport);
  });
  afterEach(() => { cleanup(); root.remove(); vi.unstubAllGlobals(); });

  function resize(height: number, offsetTop: number, scale = 1) {
    act(() => {
      Object.assign(viewport, { height, offsetTop, scale });
      viewport.dispatchEvent(new Event("resize"));
    });
  }

  it("fits the whole app to keyboard height and pan, preserving draft and focus through dismissal", () => {
    render(<AppSurface />, { container: root });
    const input = root.querySelector("textarea")!;
    input.focus();
    resize(396, 350);
    expect(root).toHaveClass("visual-viewport");
    expect(document.documentElement.style.getPropertyValue("--app-viewport-height")).toBe("396px");
    expect(document.documentElement.style.getPropertyValue("--app-viewport-top")).toBe("350px");
    act(() => {
      viewport.offsetTop = 320;
      viewport.dispatchEvent(new Event("scroll"));
    });
    expect(document.documentElement.style.getPropertyValue("--app-viewport-top")).toBe("320px");
    expect(document.activeElement).toBe(input);
    expect(input).toHaveValue("中文草稿");
    resize(746, 0);
    expect(document.documentElement.style.getPropertyValue("--app-viewport-height")).toBe("746px");
    expect(document.documentElement.style.getPropertyValue("--app-viewport-top")).toBe("0px");
  });

  it("collapses mobile chrome for the keyboard and keeps buttons stable through blur", async () => {
    render(<AppSurface />, { container: root });
    const input = root.querySelector("textarea")!;
    input.focus();
    expect(root).not.toHaveClass("soft-keyboard-open");
    resize(396, 70);
    expect(root).toHaveClass("soft-keyboard-open");
    input.blur();
    await act(async () => { await new Promise(requestAnimationFrame); });
    expect(root).toHaveClass("soft-keyboard-open");
    input.focus();
    expect(root).toHaveClass("soft-keyboard-open");
    resize(746, 0);
    expect(root).not.toHaveClass("soft-keyboard-open");
  });

  it("detects a keyboard when Android also shrinks the layout viewport", () => {
    render(<AppSurface />, { container: root });
    root.querySelector("textarea")!.focus();
    vi.stubGlobal("innerHeight", 396);
    resize(396, 0);
    expect(root).toHaveClass("soft-keyboard-open");
    vi.stubGlobal("innerWidth", 844);
    vi.stubGlobal("innerHeight", 390);
    resize(390, 0);
    expect(root).not.toHaveClass("soft-keyboard-open");
  });

  it("fits keyboard changes despite WebKit scale rounding", () => {
    render(<AppSurface />, { container: root });
    resize(396, 70, 1.0000001);
    expect(document.documentElement.style.getPropertyValue("--app-viewport-height")).toBe("396px");
    expect(document.documentElement.style.getPropertyValue("--app-viewport-top")).toBe("70px");
  });

  it("does not reflow or chase the viewport during pinch zoom, then resumes on reset", () => {
    render(<AppSurface />, { container: root });
    resize(373, 120, 2);
    expect(document.documentElement.style.getPropertyValue("--app-viewport-height")).toBe("746px");
    expect(document.documentElement.style.getPropertyValue("--app-viewport-top")).toBe("0px");
    resize(320, 0);
    expect(document.documentElement.style.getPropertyValue("--app-viewport-height")).toBe("320px");
  });

  it("keeps navigation below the top edge when a focused PWA rotates with negative WebKit overscroll", () => {
    render(<AppSurface />, { container: root });
    resize(128, -68);
    expect(root).toHaveClass("short-visual-viewport");
    expect(document.documentElement.style.getPropertyValue("--app-viewport-height")).toBe("128px");
    expect(document.documentElement.style.getPropertyValue("--app-viewport-top")).toBe("0px");
    resize(428, 416);
    expect(root).not.toHaveClass("short-visual-viewport");
    expect(document.documentElement.style.getPropertyValue("--app-viewport-top")).toBe("416px");
  });

  it.each(["desktop", "unsupported"])("leaves %s layout ownership unchanged", (kind) => {
    touch = kind !== "desktop";
    if (kind === "unsupported") vi.stubGlobal("visualViewport", undefined);
    render(<AppSurface />, { container: root });
    resize(396, 350);
    expect(root).not.toHaveClass("visual-viewport");
    expect(document.documentElement.style.getPropertyValue("--app-viewport-height")).toBe("");
  });

  it("releases listeners and owned styles when touch layout is disabled or the app unmounts", () => {
    const { rerender, unmount } = render(<AppSurface />, { container: root });
    touch = false;
    rerender(<AppSurface />);
    resize(396, 350);
    expect(root).not.toHaveClass("visual-viewport");
    expect(document.documentElement.style.getPropertyValue("--app-viewport-height")).toBe("");
    touch = true;
    rerender(<AppSurface />);
    expect(root).toHaveClass("visual-viewport");
    unmount();
    resize(746, 0);
    expect(root).not.toHaveClass("visual-viewport");
    expect(root).not.toHaveClass("short-visual-viewport");
    expect(document.documentElement.style.getPropertyValue("--app-viewport-top")).toBe("");
  });
});
