import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ClearConversationButton } from "@/components/thread/ClearConversationButton";
import { setAppLanguage } from "@/i18n";
import type { CirnoClient } from "@/lib/cirno-client";

beforeEach(async () => { await setAppLanguage("en"); });
afterEach(cleanup);
it("requires confirmation and uses the existing session reset command", async () => {
  const send = vi.fn().mockResolvedValue(undefined);
  const cleared = vi.fn();
  render(<ClearConversationButton client={{ sendSystemCommand: send } as unknown as CirnoClient} chatId="global" onCleared={cleared} />);
  fireEvent.click(screen.getByRole("button", { name: "Clear Cirno conversation" }));
  expect(send).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Clear conversation" }));
  await waitFor(() => expect(cleared).toHaveBeenCalledOnce());
  expect(send).toHaveBeenCalledWith("global", "/new", 30_000);
});
it("keeps the dialog open and shows the actual failure without clearing locally", async () => {
  const cleared = vi.fn();
  const send = vi.fn().mockRejectedValue(new Error("Connection unavailable"));
  render(<ClearConversationButton client={{ sendSystemCommand: send } as unknown as CirnoClient} chatId="global" onCleared={cleared} />);
  fireEvent.click(screen.getByRole("button", { name: "Clear Cirno conversation" }));
  fireEvent.click(screen.getByRole("button", { name: "Clear conversation" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Connection unavailable");
  expect(cleared).not.toHaveBeenCalled();
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();
});
