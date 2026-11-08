import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useState } from "react";
import { AccountRequestError, accountRequest, type AccountStatus } from "@/lib/account";
import { RouterNameSettings } from "@/features/settings/account/RouterNameSettings";
import { ConversationCatalogContext, type ConversationCatalog } from "@/features/conversations/catalog/context";
import { SessionHandleLabel } from "@/components/SessionHandleLabel";
import { GenericToolRun } from "@/components/thread/activity/GenericToolRun";
import { parseGenericToolTrace } from "@/components/thread/activity/generic-tool-model";
import type { ChatSummary } from "@/lib/contracts/conversations";
import { ROUTER_CHAT_ID, ROUTER_SESSION_KEY } from "@/lib/conversation-role";
import { setAppLanguage } from "@/i18n";

vi.mock("@/lib/account", async original => ({ ...await original<typeof import("@/lib/account")>(), accountRequest: vi.fn() }));
const initial: AccountStatus = { enabled: true, authenticated: true, registration_required: false, username: "owner", router_handle: "cirno", router_id: "handle_9daf584999d74888c635d1df82976250" };
function Settings() {
  const [account, setAccount] = useState(initial);
  return <><RouterNameSettings account={account} onSaved={setAccount} /><output>{account.router_id}</output></>;
}
beforeEach(async () => { await setAppLanguage("en"); });
afterEach(() => { cleanup(); vi.resetAllMocks(); });
function submit(value: string) {
  fireEvent.change(screen.getByRole("textbox"), { target: { value } });
  fireEvent.submit(screen.getByRole("button", { name: "Save name" }).closest("form")!);
}
it("saves a normalized display alias while retaining the fixed ID", async () => {
  vi.mocked(accountRequest).mockResolvedValue({ id: initial.router_id, name: "snow_9" });
  render(<Settings />);
  submit("@Snow_9");
  expect(await screen.findByText("Name updated.")).toBeInTheDocument();
  expect(accountRequest).toHaveBeenCalledWith("change-router-name", { router_handle: "snow_9" });
  expect(screen.getByRole("textbox")).toHaveValue("snow_9");
  expect(screen.getByText(initial.router_id!)).toBeInTheDocument();
});
it("retains rejected drafts, explains collisions, and permits a corrected retry", async () => {
  vi.mocked(accountRequest).mockRejectedValueOnce(new AccountRequestError("router_handle_taken"));
  render(<Settings />);
  submit("taken_name");
  expect(await screen.findByRole("alert")).toHaveTextContent("already uses this name");
  expect(screen.getByRole("textbox")).toHaveValue("taken_name");
  vi.mocked(accountRequest).mockResolvedValue({ id: initial.router_id, name: "available" });
  submit("available");
  expect(await screen.findByText("Name updated.")).toBeInTheDocument();
});
it("ignores a completed rename after its settings owner is replaced", async () => {
  let complete!: (value: unknown) => void;
  vi.mocked(accountRequest).mockImplementation(() => new Promise(resolve => { complete = resolve; }));
  const saved = vi.fn();
  const view = render(<RouterNameSettings account={initial} onSaved={saved} />);
  submit("snow_9");
  view.unmount();
  await act(async () => { complete({ id: initial.router_id, name: "snow_9" }); });
  await waitFor(() => expect(accountRequest).toHaveBeenCalledOnce());
  expect(saved).not.toHaveBeenCalled();
});
it("resolves source badges and compact tool targets by ID while preserving raw invocation details", () => {
  const session: ChatSummary = { key: ROUTER_SESSION_KEY, channel: "websocket", chatId: ROUTER_CHAT_ID, createdAt: null, updatedAt: null, preview: "", handle: { id: initial.router_id!, name: "snow_9" } };
  const trace = parseGenericToolTrace(`conversations__send({"to":"${initial.router_id}","content":"Report"})`)!;
  render(<ConversationCatalogContext.Provider value={{ sessions: [session] } as ConversationCatalog}>
    <SessionHandleLabel id={initial.router_id!}>@cirno</SessionHandleLabel>
    <GenericToolRun items={[{ trace, status: "done" }]} />
  </ConversationCatalogContext.Provider>);
  expect(screen.queryByText("@cirno")).not.toBeInTheDocument();
  expect(screen.getAllByText(/@snow_9/)).toHaveLength(2);
  const disclosure = screen.getByRole("button");
  fireEvent.click(disclosure);
  expect(screen.getByText(new RegExp(initial.router_id!))).toBeInTheDocument();
});
