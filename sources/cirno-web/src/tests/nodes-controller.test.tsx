import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CirnoClient } from "@/lib/cirno-client";
import type { NodeRecord } from "@/features/settings/nodes/model/contracts";
import { useNodes } from "@/features/settings/nodes/model/useNodes";

const node: NodeRecord = { id: "research", name: "Research Node", host: "example.test", port: 22, username: "owner",
  auth_method: "password", has_password: true, working_directory: "/research", identity_file: "", host_key: "" };
type Payload = { action: string; values: Record<string, unknown> };
function server(override: (payload: Payload) => unknown = () => undefined) {
  return vi.fn((_name: string, payload: Payload) => override(payload) ?? Promise.resolve(
    payload.action === "nodes.list" ? { nodes: [node], jobs: [] } : payload.action === "credentials.list" ? { records: [{ id: node.id, label: node.name, kind: "ssh", node_enabled: true }] } : { ok: true }));
}
function mount(request: ReturnType<typeof vi.fn>) {
  const client = { requestMutation: request } as unknown as CirnoClient;
  return { ...renderHook(({ currentClient }) => useNodes(currentClient), { initialProps: { currentClient: client } }), client };
}

describe("Node operations", () => {
  it("exposes a list failure and retries metadata without reading stored passwords", async () => {
    let failed = true;
    const request = server(payload => payload.action === "nodes.list" && failed ? Promise.reject("Node store unavailable") : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.listError).toBe("Node store unavailable"));
    failed = false;
    await act(async () => view.result.current.refresh());
    expect(view.result.current.nodes).toEqual([node]); expect(view.result.current.listError).toBe("");
    act(() => view.result.current.edit(node));
    expect(view.result.current.draft?.credential_id).toBe(node.id);
    expect(view.result.current.draft).not.toHaveProperty("password");
  });

  it("preserves failed Node enrollment edits, serializes writes and closes it after a successful retry", async () => {
    let failed = true;
    const request = server(payload => payload.action === "nodes.save" && failed ? Promise.reject(new Error("Could not store Node")) : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    act(() => view.result.current.edit(node));
    act(() => view.result.current.setDraft(old => old && ({ ...old, working_directory: "/new-research" })));
    await act(async () => { await Promise.all([view.result.current.save(), view.result.current.save()]); });
    expect(view.result.current.draft?.working_directory).toBe("/new-research");
    expect(view.result.current.error).toBe("Could not store Node");
    expect(request.mock.calls.filter(([, payload]) => payload.action === "nodes.save")).toHaveLength(1);
    failed = false;
    await act(async () => view.result.current.save());
    expect(view.result.current.draft).toBeNull();
    expect(request).toHaveBeenCalledWith("instance.action", { action: "nodes.save", values: expect.objectContaining({ working_directory: "/new-research", credential_id: node.id }) }, 30_000);
  });

  it("executes directly with the command timeout, reports failures and clears the command when choosing another Node", async () => {
    let failed = true;
    const request = server(payload => payload.action === "nodes.execute" ? failed ? Promise.reject(new Error("SSH connection failed")) : Promise.resolve({ output: "" }) : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    act(() => view.result.current.startCommand(node));
    act(() => view.result.current.setCommand("uname -a"));
    await act(async () => view.result.current.execute());
    expect(view.result.current.error).toBe("SSH connection failed");
    expect(view.result.current.command).toBe("uname -a"); expect(view.result.current.output).toBeNull();
    failed = false;
    await act(async () => view.result.current.execute());
    expect(view.result.current.output).toBe("");
    expect(request).toHaveBeenCalledWith("instance.action", { action: "nodes.execute", values: { id: node.id, command: "uname -a" } }, 130_000);
    act(() => view.result.current.startCommand({ ...node, id: "other-node" }));
    expect(view.result.current.command).toBe(""); expect(view.result.current.output).toBeNull();
    expect(request.mock.calls.some(([, payload]) => payload.action === "nodes.start_job")).toBe(false);
  });

  it("keeps a successful write completed if refreshing the list fails", async () => {
    let lists = 0;
    const request = server(payload => payload.action === "nodes.list" && ++lists > 1 ? Promise.reject(new Error("Metadata refresh failed")) : undefined);
    const view = mount(request);
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    act(() => view.result.current.edit(node));
    await act(async () => view.result.current.save());
    expect(view.result.current.draft).toBeNull(); expect(view.result.current.error).toBe("");
    expect(view.result.current.listError).toBe("Metadata refresh failed");
    expect(view.result.current.nodes).toEqual([node]);
  });
});

it("waits for the currently selected credential and ignores a late response from an old editor", async () => {
  const pending = new Map<string, (value: unknown) => void>();
  const request = server(payload => payload.action === "credentials.describe"
    ? new Promise(resolve => pending.set(String(payload.values.id), resolve)) : undefined);
  const view = mount(request);
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  act(() => view.result.current.edit());
  let first!: Promise<void>, second!: Promise<void>;
  act(() => { first = view.result.current.selectCredential("first"); });
  act(() => { second = view.result.current.selectCredential("second"); });
  await act(async () => { pending.get("first")!({ ssh: { working_directory: "/wrong", environment: {} } }); await first; });
  expect(view.result.current.credentialReady).toBe(false);
  expect(view.result.current.busy).toBe(true);
  await act(async () => view.result.current.save());
  expect(request.mock.calls.some(([, payload]) => payload.action === "nodes.save")).toBe(false);
  await act(async () => { pending.get("second")!({ ssh: { working_directory: "/right", environment: {} } }); await second; });
  expect(view.result.current.credentialReady).toBe(true);
  expect(view.result.current.draft?.working_directory).toBe("/right");
  let old!: Promise<void>;
  act(() => { old = view.result.current.selectCredential("old"); });
  act(() => view.result.current.setDraft(null));
  act(() => view.result.current.edit(node));
  await act(async () => { pending.get("old")!({ ssh: { working_directory: "/stale", environment: {} } }); await old; });
  expect(view.result.current.draft?.working_directory).toBe("/research");
  expect(view.result.current.busy).toBe(false);
});
