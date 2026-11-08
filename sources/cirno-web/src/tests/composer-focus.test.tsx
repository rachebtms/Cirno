import { act, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ThreadVisibilityContext } from "@/hooks/useThreadVisibility";
import { ThreadComposer } from "@/features/composer/ThreadComposer";

const nextFrame = () => act(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())));

it("only focuses the active composer when several conversation panes stay mounted", async () => {
  const send = vi.fn();
  const view = (active: string) => <>
    <ThreadComposer active={active === "a"} inputAriaLabel="Pane A" onSend={send} />
    <ThreadComposer active={active === "b"} inputAriaLabel="Pane B" onSend={send} />
  </>;
  const { rerender } = render(view("b"));
  await waitFor(() => expect(screen.getByRole("textbox", { name: "Pane B" })).toHaveFocus());
  rerender(view("a"));
  await waitFor(() => expect(screen.getByRole("textbox", { name: "Pane A" })).toHaveFocus());
  expect(send).not.toHaveBeenCalled();
});

it("cancels queued focus when the user opens another workbench tab", async () => {
  const view = (visible: boolean) => <>
    <button autoFocus>Other tab</button>
    <ThreadVisibilityContext value={visible}><ThreadComposer inputAriaLabel="Chat" onSend={vi.fn()} focusRequest={1} /></ThreadVisibilityContext>
  </>;
  const { rerender } = render(view(true));
  rerender(view(false));
  screen.getByRole("button", { name: "Other tab" }).focus();
  await nextFrame();
  expect(screen.getByRole("button", { name: "Other tab" })).toHaveFocus();
  rerender(view(true));
  await waitFor(() => expect(screen.getByRole("textbox", { name: "Chat" })).toHaveFocus());
});
