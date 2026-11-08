import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CirnoClient } from "@/lib/cirno-client";
import { useCredentialVault } from "@/features/credentials/model/useCredentialVault";

const record = { id: "account", label: "Research account", kind: "password" as const };
type Payload = { action: string; values?: Record<string, unknown> };
function pending<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }
function server(override: (payload: Payload) => unknown = () => undefined) {
  return vi.fn((_name: string, payload: Payload) => override(payload) ?? Promise.resolve(payload.action === "credentials.list"
    ? { records: [record] } : { ok: true }));
}
function mount(request: ReturnType<typeof vi.fn>) {
  const client = { requestMutation: request } as unknown as CirnoClient, dirty = vi.fn();
  const hook = renderHook(({ active, currentClient }) => useCredentialVault(currentClient, active, dirty),
    { initialProps: { active: true, currentClient: client } });
  return { ...hook, dirty, client };
}

describe("credential data ownership", () => {
  it("lists metadata without fetching secrets and exposes list failures with a retry", async () => {
    let failed = true;
    const request = server(payload => payload.action === "credentials.list" && failed ? Promise.reject("Vault is locked") : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.listError).toBe("Vault is locked"));
    failed = false;
    await act(async () => view.result.current.refresh());
    expect(view.result.current.records).toEqual([record]); expect(view.result.current.listError).toBe("");
    act(() => view.result.current.begin(record));
    expect(view.result.current.draft?.value).toBe("");
    expect(request.mock.calls.every(([, payload]) => payload.action === "credentials.list")).toBe(true);
  });

  it("discards a late reveal after the tab is hidden", async () => {
    const reveal = pending<{ value: string; username: string }>();
    const request = server(payload => payload.action === "credentials.reveal" ? reveal.promise : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    act(() => view.result.current.begin(record));
    let showing!: Promise<void>;
    act(() => { showing = view.result.current.reveal(); });
    view.rerender({ active: false, currentClient: view.client });
    expect(view.result.current.draft).toBeNull();
    await act(async () => { reveal.resolve({ value: "private-token", username: "owner" }); await showing; });
    expect(view.result.current.draft).toBeNull(); expect(view.result.current.busy).toBe(false);
  });

  it("clears an unmodified revealed value but keeps an edited draft when switching tabs", async () => {
    const request = server(payload => payload.action === "credentials.reveal" ? Promise.resolve({ value: "private-token" }) : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    act(() => view.result.current.begin(record));
    await act(async () => view.result.current.reveal());
    expect(view.dirty).toHaveBeenLastCalledWith(false);
    act(() => view.result.current.update({ value: "new-private-token" }));
    view.rerender({ active: false, currentClient: view.client });
    expect(view.result.current.draft?.value).toBe("new-private-token");
    expect(view.dirty).toHaveBeenLastCalledWith(true);
    act(() => view.result.current.clear());
    expect(view.dirty).toHaveBeenLastCalledWith(false);
    expect(view.result.current.draft).toBeNull();
  });

  it("retains user input on a failed save without submitting duplicate requests", async () => {
    const request = server(payload => payload.action === "credentials.save" ? Promise.reject(new Error("Disk is full")) : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    act(() => view.result.current.begin());
    act(() => view.result.current.update({ label: "Archive", value: "private text" }));
    await act(async () => { await Promise.all([view.result.current.save(), view.result.current.save()]); });
    expect(view.result.current.error).toBe("Disk is full");
    expect(view.result.current.draft?.value).toBe("private text");
    expect(request.mock.calls.filter(([, payload]) => payload.action === "credentials.save")).toHaveLength(1);
  });

  it("does not resubmit a successful save when refreshing the metadata fails", async () => {
    let lists = 0;
    const request = server(payload => payload.action === "credentials.list" && ++lists > 1 ? Promise.reject(new Error("Refresh failed")) : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    act(() => view.result.current.begin());
    act(() => view.result.current.update({ label: "Archive", value: "private text" }));
    await act(async () => view.result.current.save());
    expect(view.result.current.draft).toBeNull();
    expect(view.result.current.listError).toBe("Refresh failed");
    await act(async () => view.result.current.refresh());
    expect(request.mock.calls.filter(([, payload]) => payload.action === "credentials.save")).toHaveLength(1);
  });

  it("ignores an old account's save completion and never reloads its metadata into a new account", async () => {
    const saving = pending<{ ok: boolean }>();
    const request = server(payload => payload.action === "credentials.save" ? saving.promise : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    act(() => view.result.current.begin());
    act(() => view.result.current.update({ label: "Archive", value: "private text" }));
    let save!: Promise<void>;
    act(() => { save = view.result.current.save(); });
    const nextRequest = vi.fn().mockResolvedValue({ records: [{ ...record, id: "next-owner", label: "Other account" }] });
    const nextClient = { requestMutation: nextRequest } as unknown as CirnoClient;
    view.rerender({ active: true, currentClient: nextClient });
    await waitFor(() => expect(view.result.current.records[0]?.id).toBe("next-owner"));
    await act(async () => { saving.resolve({ ok: true }); await save; });
    expect(view.result.current.draft).toBeNull(); expect(view.result.current.records[0].id).toBe("next-owner");
    expect(request.mock.calls.filter(([, payload]) => payload.action === "credentials.list")).toHaveLength(1);
  });

  it("clears the editor when its record is deleted and sends no hidden username for a text record", async () => {
    const request = server(); const view = mount(request);
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    act(() => view.result.current.begin(record));
    await act(async () => view.result.current.remove(record.id));
    expect(view.result.current.draft).toBeNull();
    act(() => view.result.current.begin());
    act(() => view.result.current.update({ label: "Archive", kind: "text", username: "hidden-name", value: "private text" }));
    await act(async () => view.result.current.save());
    expect(request).toHaveBeenCalledWith("workbench.action", { action: "credentials.save", values: {
      id: undefined, label: "Archive", kind: "text", username: "", value: "private text", agent_visible: false,
    } });
  });
});

describe("SSH credential editing", () => {
  const sshRecord = { id: "ssh-record", label: "GPU", kind: "ssh" as const, agent_visible: false, node_enabled: false };
  const connection = { host: "gpu.example", port: 22, username: "owner", auth_method: "password", has_password: true,
    identity_file: "", host_key: "", node_enabled: false, working_directory: "." };
  it("enables visibility and Node access without retrieving the saved password", async () => {
    const request = server(payload => payload.action === "credentials.describe" ? Promise.resolve({ ssh: connection }) : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    act(() => view.result.current.begin(sshRecord));
    await waitFor(() => expect(view.result.current.draft?.sshLoaded).toBe(true));
    expect(view.result.current.draft?.ssh.password).toBe("");
    act(() => view.result.current.update({ agentVisible: true, nodeEnabled: true }));
    await act(async () => view.result.current.save());
    expect(request).toHaveBeenCalledWith("workbench.action", { action: "credentials.save", values: expect.objectContaining({
      agent_visible: true, node_enabled: true, ssh: expect.objectContaining({ password: "", host: "gpu.example", port: 22 }),
    }) });
    expect(request.mock.calls.some(([, payload]) => payload.action === "credentials.reveal")).toBe(false);
  });
  it("does not restore SSH details after leaving the editor", async () => {
    const details = pending<{ ssh: typeof connection }>();
    const request = server(payload => payload.action === "credentials.describe" ? details.promise : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    act(() => view.result.current.begin(sshRecord));
    view.rerender({ active: false, currentClient: view.client });
    await act(async () => details.resolve({ ssh: connection }));
    expect(view.result.current.draft).toBeNull(); expect(view.result.current.busy).toBe(false);
  });
  it("ignores an old account's SSH fingerprint scan", async () => {
    const scan = pending<{ host_key: string; fingerprints: string }>();
    const request = server(payload => payload.action === "nodes.scan" ? scan.promise : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    act(() => view.result.current.begin());
    let scanning!: Promise<void>;
    act(() => { scanning = view.result.current.scan(); });
    const nextClient = { requestMutation: server() } as unknown as CirnoClient;
    view.rerender({ active: true, currentClient: nextClient });
    await act(async () => { scan.resolve({ host_key: "old-key", fingerprints: "old-fingerprint" }); await scanning; });
    expect(view.result.current.draft).toBeNull(); expect(view.result.current.fingerprints).toBe("");
  });
});
