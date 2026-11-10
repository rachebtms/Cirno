import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useStripReorder } from "@/features/workbench/ui/useStripReorder";

function Harness({ click }: { click: () => void }) {
  const strip = useStripReorder(["one", "two"], () => {});
  return <div data-testid="strip" data-active={strip.dragged} {...strip.handlers}>
    <button data-reorder-id="one">One</button><button data-reorder-id="two" onClick={click}>Two</button>
  </div>;
}
function start(click: () => void) {
  render(<Harness click={click} />);
  const strip = screen.getByTestId("strip"), one = screen.getByRole("button", { name: "One" });
  strip.setPointerCapture = vi.fn(); strip.hasPointerCapture = () => true; strip.releasePointerCapture = vi.fn();
  document.elementFromPoint = () => one;
  fireEvent.pointerDown(one, { pointerId: 11, pointerType: "mouse", button: 0, clientX: 10, clientY: 10 });
  fireEvent.pointerMove(window, { pointerId: 11, clientX: 25, clientY: 10 });
  expect(strip).toHaveAttribute("data-active", "one");
  return strip;
}
it("does not swallow the next launcher click after pointer cancellation", () => {
  const click = vi.fn();
  const strip = start(click);
  fireEvent.pointerCancel(window, { pointerId: 11 });
  expect(strip).not.toHaveAttribute("data-active");
  fireEvent.click(screen.getByRole("button", { name: "Two" }));
  expect(click).toHaveBeenCalledTimes(1);
});
it("ignores another pointer's release and ends only the pointer that owns the drag", () => {
  const strip = start(vi.fn());
  fireEvent.pointerUp(window, { pointerId: 22 });
  expect(strip).toHaveAttribute("data-active", "one");
  expect(strip.releasePointerCapture).not.toHaveBeenCalled();
  fireEvent.pointerUp(window, { pointerId: 11 });
  expect(strip).not.toHaveAttribute("data-active");
  expect(strip.releasePointerCapture).toHaveBeenCalledWith(11);
});
