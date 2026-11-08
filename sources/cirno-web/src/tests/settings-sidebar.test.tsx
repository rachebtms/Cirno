import { useState } from "react";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { SettingsNavigation } from "@/features/settings/ui/SettingsNavigation";
import type { SettingsSectionKey } from "@/features/settings/contracts";
import { installSettingsViewTestHooks, renderSettingsView, settingsPayload } from "@/tests/settings-test-utils";

installSettingsViewTestHooks();
afterEach(cleanup);
function media(initial: boolean) {
  const target = new EventTarget();
  const value = { matches: initial, media: "(max-width: 1023px)", onchange: null,
    addListener: vi.fn(), removeListener: vi.fn(), addEventListener: target.addEventListener.bind(target),
    removeEventListener: target.removeEventListener.bind(target), dispatchEvent: target.dispatchEvent.bind(target) };
  vi.stubGlobal("matchMedia", vi.fn(() => value));
  return (next: boolean) => act(() => { value.matches = next; target.dispatchEvent(new Event("change")); });
}
function Navigation({ onRestart, restartPending = false }: { onRestart?: () => void; restartPending?: boolean }) {
  const [active, select] = useState<SettingsSectionKey>("models");
  return <SettingsNavigation activeSection={active} onSelectSection={select} onBackToChat={() => {}} onRestart={onRestart} restartPending={restartPending} />;
}
it("searches desktop categories and navigates without mixing Memory and Personality", async () => {
  media(false); const user = userEvent.setup(); render(<Navigation />);
  const list = screen.getByRole("navigation", { name: "Settings sections" });
  expect(within(list).getByRole("button", { name: "Models" })).toHaveAttribute("aria-current", "page");
  await user.type(screen.getByRole("searchbox"), "memory");
  expect(screen.queryByRole("button", { name: "Personality" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Memory library" }));
  expect(screen.getByRole("button", { name: "Memory library" })).toHaveAttribute("aria-current", "page");
  await user.clear(screen.getByRole("searchbox"));
  await user.click(screen.getByRole("button", { name: "Personality" }));
  expect(screen.getByRole("button", { name: "Personality" })).toHaveAttribute("aria-current", "page");
});
it("opens searchable mobile navigation, chooses a category and returns focus", async () => {
  media(true); const user = userEvent.setup(); render(<Navigation />);
  await user.click(screen.getByRole("button", { name: "Settings: Models" }));
  const dialog = screen.getByRole("dialog", { name: "Settings" });
  await user.type(within(dialog).getByRole("searchbox"), "appearance");
  await user.click(within(dialog).getByRole("button", { name: "Appearance" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Settings: Appearance" })).toHaveFocus();
});
it("closes mobile navigation with Escape without changing the category", async () => {
  media(true); const user = userEvent.setup(); render(<Navigation />);
  const trigger = screen.getByRole("button", { name: "Settings: Models" }); await user.click(trigger);
  await user.keyboard("{Escape}"); await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(trigger).toHaveFocus();
});
it("does not reopen an old mobile navigation dialog after resizing", async () => {
  const resize = media(true); const user = userEvent.setup(); render(<Navigation />);
  await user.click(screen.getByRole("button", { name: "Settings: Models" }));
  resize(false); await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Models" })).toBeVisible();
  resize(true); expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
it("keeps restart status and its action available in mobile navigation", async () => {
  media(true); const restart = vi.fn(); const user = userEvent.setup(); render(<Navigation onRestart={restart} restartPending />);
  expect(screen.getByRole("status")).toHaveTextContent("Restart to apply");
  await user.click(screen.getByRole("button", { name: "Settings: Models" }));
  await user.click(screen.getByRole("button", { name: "Restart" })); expect(restart).toHaveBeenCalledOnce();
});
it("retains the pending-restart exit choice in the settings application", async () => {
  media(true); const user = userEvent.setup(); const back = vi.fn();
  renderSettingsView({ initialSection: "models", initialSettings: { ...settingsPayload(), requires_restart: true }, onBackToChat: back });
  await user.click(screen.getByRole("button", { name: "Back to chat" }));
  const dialog = screen.getByRole("dialog", { name: "Restart before leaving?" });
  expect(back).not.toHaveBeenCalled(); await user.click(within(dialog).getByRole("button", { name: "Restart later" }));
  expect(back).toHaveBeenCalledOnce();
});
