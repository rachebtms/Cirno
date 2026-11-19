import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AutomationDetailDialog } from "@/features/automations/detail/AutomationDetailDialog";
import { fetchAutomationChats } from "@/lib/api";
import { setAppLanguage } from "@/i18n";
import type { AutomationChatsPayload, SessionAutomationJob } from "@/lib/contracts/automations";

vi.mock("@/lib/api", () => ({ fetchAutomationChats: vi.fn() }));
const source = { id: "source", title: "My planning", channel: "websocket" };
const target = { id: "target", title: "Previous account destination", channel: "telegram" };
const choices: AutomationChatsPayload = { revision: "rev-1", current: source, chats: [source, target] };
const job: SessionAutomationJob = {
  id: "daily", name: "Daily report", enabled: true, chat_binding_revision: "rev-1",
  schedule: { kind: "every", every_ms: 86400000 }, state: {},
  payload: { message: "Summarize the work." }, origin: { ...source, session_key: "websocket:source" },
};
const props = { open: true, locale: "en", actionKey: null, error: null,
  onOpenChange: vi.fn(), onAction: vi.fn(), onRequestEdit: vi.fn(), onRequestDelete: vi.fn() };
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
beforeEach(async () => { vi.resetAllMocks(); await setAppLanguage("en"); });
afterEach(cleanup);

it("retires loaded chat choices when authentication changes with the same job id and revision", async () => {
  const next = deferred<AutomationChatsPayload>();
  vi.mocked(fetchAutomationChats).mockResolvedValueOnce({ ...choices, current: target }).mockReturnValueOnce(next.promise);
  const save = vi.fn();
  const { rerender } = render(<AutomationDetailDialog {...props} token="first" job={job} onChangeChat={save} />);
  await waitFor(() => expect(screen.getByRole("button", { name: /Run in chat$/ })).toBeEnabled());
  expect(screen.getByRole("button", { name: /Run in chat$/ })).toHaveTextContent(target.title);
  rerender(<AutomationDetailDialog {...props} token="second" job={job} onChangeChat={save} />);
  const pending = screen.getByRole("button", { name: /Run in chat$/ });
  expect(pending).toBeDisabled();
  expect(pending).not.toHaveTextContent(target.title);
  await act(async () => next.resolve({ ...choices, chats: [source] }));
  expect(screen.getByRole("button", { name: /Run in chat$/ })).toBeEnabled();
  expect(fetchAutomationChats).toHaveBeenCalledTimes(2);
});

it("does not publish an old account's save completion into the replacement binding view", async () => {
  const pending = deferred<void>();
  const save = vi.fn(() => pending.promise);
  vi.mocked(fetchAutomationChats).mockResolvedValue(choices);
  const { rerender } = render(<AutomationDetailDialog {...props} token="first" job={job} onChangeChat={save} />);
  await waitFor(() => expect(screen.getByRole("button", { name: /Run in chat$/ })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: /Run in chat$/ }));
  fireEvent.click(await screen.findByRole("option", { name: /Previous account destination/ }));
  await userEvent.click(await screen.findByRole("button", { name: "Confirm change" }));
  expect(save).toHaveBeenCalledOnce();
  rerender(<AutomationDetailDialog {...props} token="second" job={job} onChangeChat={save} />);
  await act(async () => pending.resolve());
  await waitFor(() => expect(screen.getByRole("button", { name: /Run in chat$/ })).toBeEnabled());
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Run in chat$/ })).toHaveTextContent(source.title);
  expect(fetchAutomationChats).toHaveBeenCalledTimes(2);
});
