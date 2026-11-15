import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { useRef } from "react";
import { useHorizontalStripScroll } from "@/features/workbench/ui/useHorizontalStripScroll";

afterEach(cleanup);
function Strip({ id = "strip" }: { id?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useHorizontalStripScroll(ref);
  return <div data-testid={id} ref={ref} style={{ lineHeight: "20px", fontSize: "16px" }} />;
}
function wheel(strip: HTMLElement, values: WheelEventInit) {
  const event = new WheelEvent("wheel", { bubbles: true, cancelable: true, ...values });
  // Happy DOM models WheelEvent as UIEvent and omits MouseEvent modifiers.
  Object.defineProperties(event, { ctrlKey: { value: values.ctrlKey ?? false }, metaKey: { value: values.metaKey ?? false } });
  strip.dispatchEvent(event);
  return event;
}

it.each([
  { deltaY: 120, expected: 120 }, { deltaY: -60, expected: -60 },
  { deltaX: 80, expected: 80 }, { deltaX: 90, deltaY: 30, expected: 90 },
  { deltaX: 3, deltaY: 60, expected: 60 }, { deltaY: 2, deltaMode: 1, expected: 40 },
  { deltaY: 1, deltaMode: 2, expected: 240 }, { deltaY: 80, shiftKey: true, expected: 80 },
])("uses horizontal input without diagonal double-scrolling: %j", ({ expected, ...input }) => {
  const { getByTestId } = render(<Strip />);
  const strip = getByTestId("strip");
  Object.defineProperty(strip, "clientWidth", { value: 240 });
  expect(wheel(strip, input).defaultPrevented).toBe(true);
  expect(strip.scrollLeft).toBe(expected);
  expect(strip.scrollTop).toBe(0);
});

it("preserves zoom gestures, independent split strips and listener cleanup", () => {
  const { getByTestId, unmount } = render(<><Strip /><Strip id="other" /></>);
  const strip = getByTestId("strip"), other = getByTestId("other");
  expect(wheel(strip, { deltaY: 80, ctrlKey: true }).defaultPrevented).toBe(false);
  expect(wheel(strip, { deltaY: 80, metaKey: true }).defaultPrevented).toBe(false);
  expect(strip.scrollLeft).toBe(0);
  wheel(strip, { deltaY: 80 });
  expect(other.scrollLeft).toBe(0);
  unmount();
  expect(wheel(strip, { deltaY: 80 }).defaultPrevented).toBe(false);
  expect(strip.scrollLeft).toBe(80);
});
