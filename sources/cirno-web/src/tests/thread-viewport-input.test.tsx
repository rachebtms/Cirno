import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ThreadViewport } from "@/components/thread/ThreadViewport";
import type { UIMessage } from "@/lib/contracts/messages";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function message(id: string, content: string): UIMessage {
  return { id, role: "user", content, createdAt: 1 };
}

it.each([false, true])("retains a detached touch target through updates; conversation reset=%s", (reset) => {
  const originalLoad = vi.fn();
  const latestLoad = vi.fn();
  const props = { isStreaming: false, hasMoreBefore: true, conversationKey: "first" };
  const { container, rerender } = render(<ThreadViewport {...props}
    messages={[message("original", "Original question")]} onLoadOlder={originalLoad} />);
  const scroller = container.querySelector<HTMLElement>(".thread-message-viewport")!;
  Object.defineProperties(scroller, {
    scrollHeight: { configurable: true, value: 1800 },
    clientHeight: { configurable: true, value: 600 },
    scrollTop: { configurable: true, writable: true, value: 0 },
  });
  const target = scroller.querySelector<HTMLElement>("[data-thread-display-unit]")!;
  fireEvent.touchStart(target, { touches: [{ clientX: 100, clientY: 200 }] });
  fireEvent.touchMove(target, { touches: [{ clientX: 100, clientY: 380 }], cancelable: true });
  const attach = vi.spyOn(scroller, "addEventListener");
  const detach = vi.spyOn(scroller, "removeEventListener");

  for (let index = 0; index < 24; index++) {
    rerender(<ThreadViewport {...props} conversationKey={reset ? "second" : "first"}
      messages={[message("replacement", `Updated question ${index}`)]} onLoadOlder={latestLoad} />);
  }
  expect(target.isConnected).toBe(false);
  const inputEvents = new Set(["wheel", "touchstart", "touchmove", "touchend", "touchcancel", "pointerdown", "keydown"]);
  expect(attach.mock.calls.filter(([event]) => inputEvents.has(event))).toHaveLength(0);
  expect(detach.mock.calls.filter(([event]) => inputEvents.has(event))).toHaveLength(0);
  fireEvent.touchEnd(target);
  expect(originalLoad).not.toHaveBeenCalled();
  expect(latestLoad).toHaveBeenCalledTimes(reset ? 0 : 1);
});
