import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { BackupSettings } from "@/features/settings/system/BackupSettings";
import { CirnoClient } from "@/lib/cirno-client";
import { setAppLanguage } from "@/i18n";

const catalog = { instance: "/instance", selected: [], recommended: [], pending_restore: false };
const manifest = { id: "staged", instance: "/old", version: "0.2.19", created_at: "2026-11-18T00:00:00Z", extras: [] };
function pending<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function source() {
  const client = new CirnoClient({ url: "ws://localhost", reconnect: false });
  const api = vi.spyOn(client, "backupRequest").mockResolvedValue(catalog);
  return { client, api };
}
async function ready() { await waitFor(() => expect(screen.getByRole("button", { name: "Export backup" })).toBeEnabled()); }
function upload() {
  fireEvent.change(screen.getByLabelText("Import backup", { selector: "input" }), {
    target: { files: [new File(["tiny fixture"], "fixture.tar.gz")] },
  });
}
beforeEach(async () => {
  await setAppLanguage("en");
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("does not start a download after the backup page is unmounted", async () => {
  const { client, api } = source(), exported = pending<unknown>();
  const view = render(<BackupSettings client={client} onRestart={vi.fn()} />);
  await ready();
  api.mockImplementationOnce(() => exported.promise);
  fireEvent.click(screen.getByRole("button", { name: "Export backup" }));
  view.unmount();
  await act(async () => { exported.resolve({ url: "/old-download", filename: "old.tar.gz" }); });
  expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled();
});

it("retires an old upload preview when the connected client is replaced", async () => {
  const first = source(), second = source(), uploaded = pending<unknown>();
  second.api.mockResolvedValue({ ...catalog, instance: "/replacement" });
  const restart = vi.fn();
  const view = render(<BackupSettings client={first.client} onRestart={restart} />);
  await ready();
  first.api.mockImplementationOnce(() => uploaded.promise);
  upload();
  view.rerender(<BackupSettings client={second.client} onRestart={restart} />);
  await screen.findByText("/replacement");
  await act(async () => { uploaded.resolve(manifest); });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Export backup" })).toBeEnabled();
});

it("does not restart a replacement instance after the old restore request finishes", async () => {
  const first = source(), second = source(), restored = pending<unknown>();
  const restart = vi.fn();
  const view = render(<BackupSettings client={first.client} onRestart={restart} />);
  await ready();
  first.api.mockResolvedValueOnce(manifest);
  upload();
  await screen.findByRole("dialog");
  first.api.mockImplementationOnce(() => restored.promise);
  fireEvent.click(screen.getByRole("button", { name: "Restore and restart" }));
  view.rerender(<BackupSettings client={second.client} onRestart={restart} />);
  await act(async () => { restored.resolve({ restart_required: true }); });
  expect(restart).not.toHaveBeenCalled();
  expect(screen.queryByText("A restore is staged. Restart to apply it, or cancel it.")).not.toBeInTheDocument();
});

it("admits only one pending-restore cancellation before busy is rendered", async () => {
  const { client, api } = source(), cancelled = pending<unknown>();
  api.mockResolvedValueOnce({ ...catalog, pending_restore: true });
  render(<BackupSettings client={client} onRestart={vi.fn()} />);
  const button = await screen.findByRole("button", { name: "Cancel" });
  api.mockImplementation(() => cancelled.promise);
  act(() => { button.click(); button.click(); });
  const calls = api.mock.calls.filter(([action]) => action === "cancel");
  await act(async () => { cancelled.resolve({ ok: true }); });
  expect(calls).toHaveLength(1);
});

it("waits for the initial selection before accepting path edits", async () => {
  const { client, api } = source(), read = pending<unknown>();
  api.mockImplementationOnce(() => read.promise);
  render(<BackupSettings client={client} onRestart={vi.fn()} />);
  expect(screen.getByRole("textbox", { name: "Absolute file or folder path" })).toBeDisabled();
  await act(async () => { read.resolve(catalog); });
  expect(screen.getByRole("textbox", { name: "Absolute file or folder path" })).toBeEnabled();
});

it("keeps the accepted restore visible when restarting fails", async () => {
  const { client, api } = source();
  const restart = vi.fn().mockRejectedValue(new Error("Fixture restart unavailable"));
  render(<BackupSettings client={client} onRestart={restart} />);
  await ready();
  api.mockResolvedValueOnce(manifest);
  upload();
  await screen.findByRole("dialog");
  api.mockResolvedValueOnce({ restart_required: true });
  fireEvent.click(screen.getByRole("button", { name: "Restore and restart" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Fixture restart unavailable");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Restart now" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
});

it("removes an existing download link and extra selection on client replacement", async () => {
  const first = source(), second = source();
  first.api.mockResolvedValueOnce({ ...catalog, selected: ["/old-extra"] });
  const view = render(<BackupSettings client={first.client} onRestart={vi.fn()} />);
  await ready();
  first.api.mockResolvedValueOnce({ url: "/old-download", filename: "old.tar.gz" });
  fireEvent.click(screen.getByRole("button", { name: "Export backup" }));
  await screen.findByRole("link", { name: "Download backup" });
  view.rerender(<BackupSettings client={second.client} onRestart={vi.fn()} />);
  await ready();
  expect(screen.queryByRole("link", { name: "Download backup" })).not.toBeInTheDocument();
  expect(screen.queryByText("/old-extra")).not.toBeInTheDocument();
});
