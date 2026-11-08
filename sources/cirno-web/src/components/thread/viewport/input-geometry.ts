
export function isKeyboardEditableElement(element: Element | null): element is HTMLElement {
  if (!(element instanceof HTMLElement)) return false;
  if (element.isContentEditable) return true;
  if (element instanceof HTMLTextAreaElement) return true;
  if (!(element instanceof HTMLInputElement)) return false;
  return ![
    "button",
    "checkbox",
    "color",
    "file",
    "hidden",
    "image",
    "radio",
    "range",
    "reset",
    "submit",
  ].includes(element.type);
}

export function isThreadDisclosureTarget(target: EventTarget | null): boolean {
  return target instanceof Element
    && target.closest("[data-thread-disclosure]") !== null;
}

export function isKeyboardControl(element: Element | null): boolean {
  return element instanceof HTMLElement
    && element.closest(
      "button, a[href], select, [role='button'], [role='menuitem'], [role='option']",
    ) !== null;
}

export type ThreadScrollDirection = "backward" | "forward";

export const KEYBOARD_SCROLL_DIRECTIONS: Readonly<
  Partial<Record<string, ThreadScrollDirection>>
> = {
  ArrowUp: "backward",
  PageUp: "backward",
  Home: "backward",
  ArrowDown: "forward",
  PageDown: "forward",
  End: "forward",
};

export function directionFromDelta(deltaY: number): ThreadScrollDirection | null {
  return deltaY < 0 ? "backward" : deltaY > 0 ? "forward" : null;
}

export function keyboardScrollDirection(
  event: KeyboardEvent,
): ThreadScrollDirection | null {
  if (event.key === " ") {
    return event.shiftKey ? "backward" : "forward";
  }
  return KEYBOARD_SCROLL_DIRECTIONS[event.key] ?? null;
}

export function canScrollInDirection(
  element: HTMLElement,
  direction: ThreadScrollDirection | null,
): boolean {
  switch (direction) {
    case "backward":
      return element.scrollTop > 0;
    case "forward":
      return (
        element.scrollTop
        < Math.max(0, element.scrollHeight - element.clientHeight)
      );
    default:
      return false;
  }
}
