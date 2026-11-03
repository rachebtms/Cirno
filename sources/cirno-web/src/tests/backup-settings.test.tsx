import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { BackupSettings } from "@/components/settings/system/BackupSettings";
import { CirnoClient } from "@/lib/cirno-client";
import { setAppLanguage } from "@/i18n";

const catalog = { instance: "/data/cirno", selected: ["/work/research"], pending_restore: false, recommended: [
  { path: "/data/cirno/state/cli/config/tea", kind: "tools", included: true, directory: true },
  { path: "/work/research", kind: "workspace", included: false, directory: true },
  { path: "/home/owner/.config/gh", kind: "tools", included: false, directory: true },
] };
beforeEach(async () => { await setAppLanguage("en"); vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {}); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("offers old workspaces and credential folders while avoiding duplicate instance data", async () => {
  const client = new CirnoClient({ url: "ws://localhost", reconnect: false });
  const api = vi.spyOn(client, "backupRequest").mockResolvedValue(catalog);
  render(<BackupSettings client={client} onRestart={vi.fn()} />);
  expect(await screen.findByRole("checkbox", { name: "/data/cirno/state/cli/config/tea" })).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox", { name: "/home/owner/.config/gh" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Absolute file or folder path" }), { target: { value: "/mnt/other" } });
  fireEvent.click(screen.getByRole("button", { name: "Add path" }));
  api.mockResolvedValueOnce({ url: "/api/backups/download?ticket=test", filename: "test.tar.gz" });
  fireEvent.click(screen.getByRole("button", { name: "Export backup" }));
  await waitFor(() => expect(api).toHaveBeenCalledWith("export", { paths: ["/work/research", "/home/owner/.config/gh", "/mnt/other"] }));
  expect(await screen.findByRole("link", { name: "Download backup" })).toHaveAttribute("href", "/api/backups/download?ticket=test");
});

it("previews an import and requires explicit restore before restarting", async () => {
  const client = new CirnoClient({ url: "ws://localhost", reconnect: false });
  const api = vi.spyOn(client, "backupRequest").mockResolvedValue(catalog);
  const restart = vi.fn();
  render(<BackupSettings client={client} onRestart={restart} />);
  await screen.findByRole("checkbox", { name: "/work/research" });
  api.mockResolvedValueOnce({ id: "staged", version: "0.1.4", created_at: "2026-11-03T00:00:00Z", instance: "/original", extras: [{ path: "/old/research", archive: "extras/0", directory: true }] });
  fireEvent.change(screen.getByLabelText("Import backup", { selector: "input" }), { target: { files: [new File(["archive"], "backup.tar.gz")] } });
  expect(await screen.findByRole("dialog")).toBeVisible();
  expect(restart).not.toHaveBeenCalled();
  fireEvent.change(screen.getByRole("textbox", { name: "/old/research" }), { target: { value: "/new/research" } });
  api.mockResolvedValueOnce({ restart_required: true });
  fireEvent.click(screen.getByRole("button", { name: "Restore and restart" }));
  await waitFor(() => expect(restart).toHaveBeenCalledOnce());
  expect(api).toHaveBeenCalledWith("restore", { id: "staged", extras: { "extras/0": "/new/research" } });
});
