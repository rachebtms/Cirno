import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { TelegramBindingSettings } from "@/components/settings/channels/TelegramBindingSettings";
import type { CirnoClient } from "@/lib/cirno-client";
import { setAppLanguage } from "@/i18n";

beforeEach(async () => { await setAppLanguage("en"); });
afterEach(() => { cleanup(); vi.useRealTimers(); });
const unbound = { bound: false, enabled: true, notifications: ["cirno", "operations", "conversations", "system"], webui_url: "" };
it("shows an expiring PIN, refreshes it automatically and stops polling once bound", async () => {
  vi.useFakeTimers();
  let bound = false;
  let pins = 0;
  const requestMutation = vi.fn(async (_method, payload) => {
    if (payload.action === "telegram.pin") return { pin: ++pins === 1 ? "12345678" : "87654321", expires_at: Date.now() + 2000, ttl_seconds: 2 };
    return bound ? { ...unbound, bound: true, username: "owner", user_id: "123" } : unbound;
  });
  render(<TelegramBindingSettings client={{ requestMutation } as unknown as CirnoClient} onConfigure={() => {}} />);
  await act(async () => Promise.resolve());
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Generate PIN" })));
  expect(screen.getByLabelText("Pairing PIN")).toHaveTextContent("12345678");
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(screen.getByLabelText("Pairing PIN")).toHaveTextContent("87654321");
  bound = true;
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(screen.getByText("@owner")).toBeInTheDocument();
  expect(screen.queryByLabelText("Pairing PIN")).not.toBeInTheDocument();
  const calls = requestMutation.mock.calls.length;
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(requestMutation).toHaveBeenCalledTimes(calls);
});
it("persists Telegram notification categories independently of browser preferences", async () => {
  const requestMutation = vi.fn(async (_method, payload) => ({ ...unbound, ...payload.values }));
  render(<TelegramBindingSettings client={{ requestMutation } as unknown as CirnoClient} onConfigure={() => {}} />);
  const control = await screen.findByRole("switch", { name: "Actions" });
  fireEvent.click(control);
  await waitFor(() => expect(requestMutation).toHaveBeenCalledWith("instance.action", {
    action: "telegram.settings", values: { notifications: ["cirno", "conversations", "system"] },
  }));
});
it("shows the server reason when generating a PIN fails", async () => {
  const requestMutation = vi.fn(async (_method, payload) => {
    if (payload.action === "telegram.pin") throw new Error("Binding store unavailable");
    return unbound;
  });
  render(<TelegramBindingSettings client={{ requestMutation } as unknown as CirnoClient} onConfigure={() => {}} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Generate PIN" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Generate PIN" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Binding store unavailable");
});
