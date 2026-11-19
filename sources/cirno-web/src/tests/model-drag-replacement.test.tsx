import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useModelPresetDrag } from "@/features/settings/models/useModelPresetDrag";

afterEach(cleanup);

function DragList({ keys, disabled = false, save }: { keys: string[]; disabled?: boolean; save: (keys: string[]) => void }) {
  const drag = useModelPresetDrag({ keys, disabled, onReorder: save });
  return <div ref={drag.listRef} {...drag.listProps} data-testid="list" data-dragged={drag.draggedKey}>
    <output>{drag.previewKeys.join(",")}</output>
    {keys.map(key => <div key={key} data-preset-sort-key={key}>
      <div data-preset-sort-surface={key}><button onPointerDown={event => drag.start(event, key)}>{key}</button></div>
    </div>)}
  </div>;
}

function beginDrag() {
  const frames = vi.spyOn(globalThis, "requestAnimationFrame").mockReturnValue(71);
  const cancel = vi.spyOn(globalThis, "cancelAnimationFrame").mockImplementation(() => {});
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const key = this.dataset.presetSortSurface ?? this.dataset.presetSortKey;
    return new DOMRect(0, key === "b" ? 60 : 10, 100, 40);
  });
  fireEvent.pointerDown(screen.getByRole("button", { name: "a" }), { button: 0, pointerId: 1, clientY: 20 });
  fireEvent.pointerMove(screen.getByTestId("list"), { buttons: 1, pointerId: 1, clientY: 100 });
  expect(screen.getByTestId("list")).toHaveAttribute("data-dragged", "a");
  expect(screen.getByRole("status")).toHaveTextContent("b,a");
  expect(frames).toHaveBeenCalled();
  return cancel;
}

it.each([
  { name: "busy operation", keys: ["a", "b"], disabled: true },
  { name: "removed preset", keys: ["b"], disabled: false },
  { name: "replacement call order", keys: ["b", "a"], disabled: false },
])("cancels drag after $name instead of saving an obsolete order", ({ keys, disabled }) => {
  const save = vi.fn();
  const view = render(<DragList keys={["a", "b"]} save={save} />);
  const cancel = beginDrag();
  view.rerender(<DragList keys={keys} disabled={disabled} save={save} />);
  expect(screen.getByTestId("list")).not.toHaveAttribute("data-dragged");
  expect(screen.getByRole("status")).toHaveTextContent(keys.join(","));
  expect(cancel).toHaveBeenCalledWith(71);
  fireEvent.pointerUp(screen.getByTestId("list"), { pointerId: 1 });
  expect(save).not.toHaveBeenCalled();
});

it("allows an equal-key rerender during a drag and saves the user's order", () => {
  const save = vi.fn();
  const view = render(<DragList keys={["a", "b"]} save={save} />);
  beginDrag();
  view.rerender(<DragList keys={["a", "b"]} save={save} />);
  expect(screen.getByTestId("list")).toHaveAttribute("data-dragged", "a");
  fireEvent.pointerUp(screen.getByTestId("list"), { pointerId: 1 });
  expect(save).toHaveBeenCalledWith(["b", "a"]);
});

it.each(["pointerUp", "pointerCancel", "lostPointerCapture"] as const)(
  "ignores another pointer's %s while the owning pointer is dragging", event => {
    const save = vi.fn();
    render(<DragList keys={["a", "b"]} save={save} />);
    beginDrag();
    fireEvent[event](screen.getByTestId("list"), { pointerId: 2 });
    expect(save).not.toHaveBeenCalled();
    expect(screen.getByTestId("list")).toHaveAttribute("data-dragged", "a");
    fireEvent.pointerUp(screen.getByTestId("list"), { pointerId: 1 });
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith(["b", "a"]);
  },
);

it("does not replace an active gesture when another pointer presses a drag handle", () => {
  const save = vi.fn();
  render(<DragList keys={["a", "b"]} save={save} />);
  beginDrag();
  fireEvent.pointerDown(screen.getByRole("button", { name: "b" }), { button: 0, pointerId: 2, clientY: 70 });
  fireEvent.pointerUp(screen.getByTestId("list"), { pointerId: 2 });
  expect(save).not.toHaveBeenCalled();
  fireEvent.pointerUp(screen.getByTestId("list"), { pointerId: 1 });
  expect(save).toHaveBeenCalledWith(["b", "a"]);
  expect(screen.getByTestId("list")).not.toHaveAttribute("data-dragged");
});
