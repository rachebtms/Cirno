import { useCallback, useEffect, useRef, useState } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import { emptySSH, type CredentialDraft, type CredentialInfo, type CredentialPatch, type SSHResponse } from "./contracts";

export function useCredentialVault(client: CirnoClient, active: boolean, onDirtyChange?: (dirty: boolean) => void) {
  const [records, setRecords] = useState<CredentialInfo[]>([]);
  const [draft, setDraft] = useState<CredentialDraft | null>(null);
  const [error, setError] = useState("");
  const [listError, setListError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [describing, setDescribing] = useState(false), [fingerprints, setFingerprints] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);
  const epoch = useRef(0), listing = useRef(0), locked = useRef(false);
  const request = useCallback(<T,>(action: string, values = {}) =>
    client.requestMutation<T>("workbench.action", { action: `credentials.${action}`, values }), [client]);
  const fail = (reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason));
  const clear = useCallback(() => { epoch.current++; setDraft(null); setDescribing(false); setFingerprints(""); }, []);
  const refresh = useCallback(async () => {
    const revision = ++listing.current;
    setLoading(true);
    try {
      const body = await request<{ records: CredentialInfo[] }>("list");
      if (listing.current === revision) { setRecords(body.records); setListError(""); }
    } catch (reason) { if (listing.current === revision) setListError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (listing.current === revision) setLoading(false); }
  }, [request]);
  useEffect(() => {
    clear(); setError(""); setRecords([]);
    return () => { listing.current++; epoch.current++; };
  }, [clear, request]);
  useEffect(() => { if (active) void refresh(); }, [active, refresh]);
  useEffect(() => {
    onDirtyChange?.(!!draft?.modified);
    return () => onDirtyChange?.(false);
  }, [draft?.modified, onDirtyChange]);
  useEffect(() => { if (!active && draft?.id && !draft.modified) clear(); }, [active, draft, clear]);
  const begin = (record?: CredentialInfo) => {
    epoch.current++; setError(""); setDeleting(null); setFingerprints(""); setDescribing(false);
    setDraft({ id: record?.id, label: record?.label ?? "", kind: record?.kind ?? "text", username: "", value: "", modified: false, agentVisible: record?.agent_visible ?? false,
      ssh: emptySSH(), sshLoaded: !record || record.kind !== "ssh", nodeEnabled: record?.node_enabled ?? false, workingDirectory: "." });
    if (record?.kind === "ssh") void loadSSH(record.id);
  };
  const update = (patch: CredentialPatch) =>
    setDraft(old => old && ({ ...old, ...patch, modified: true }));
  async function operate(task: (revision: number) => Promise<void>) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError("");
    const revision = epoch.current;
    try { await task(revision); }
    catch (reason) { if (epoch.current === revision) fail(reason); }
    finally { locked.current = false; setBusy(false); }
  }
  async function loadSSH(id = draft!.id!) {
    const revision = epoch.current;
    setDescribing(true); setError("");
    try {
      const body = await request<{ ssh: SSHResponse }>("describe", { id });
      const { node_enabled, working_directory, ...connection } = body.ssh;
      if (epoch.current === revision) setDraft(old => old && ({ ...old, ssh: { ...connection, password: "", port: String(connection.port) },
        sshLoaded: true, nodeEnabled: node_enabled, workingDirectory: working_directory }));
    } catch (reason) { if (epoch.current === revision) fail(reason); }
    finally { if (epoch.current === revision) setDescribing(false); }
  }
  const scan = () => operate(async revision => {
    const body = await client.requestMutation<{ host_key: string; fingerprints: string }>("instance.action", {
      action: "nodes.scan", values: { host: draft!.ssh.host, port: Number(draft!.ssh.port) },
    });
    if (epoch.current === revision) {
      setDraft(old => old && ({ ...old, ssh: { ...old.ssh, host_key: body.host_key }, modified: true }));
      setFingerprints(body.fingerprints);
    }
  });
  const reveal = () => operate(async revision => {
    const body = await request<{ value: string; username?: string; ssh?: SSHResponse }>("reveal", { id: draft!.id });
    if (epoch.current === revision) setDraft(old => old && (body.ssh ? { ...old, ssh: { ...old.ssh, password: body.ssh.password } } : { ...old, value: body.value, username: body.username ?? "" }));
  });
  const save = () => operate(async revision => {
    const { id, label, kind, value, username } = draft!;
    if (kind === "ssh") {
      const { host, port, username, auth_method, password, identity_file, host_key } = draft!.ssh;
      await request("save", { id, label, kind, ssh: { host, port: Number(port), username, auth_method, password, identity_file, host_key },
        node_enabled: draft!.nodeEnabled, working_directory: draft!.workingDirectory, agent_visible: draft!.agentVisible });
    } else await request("save", { id, label, kind, value, username: kind === "password" ? username : "", agent_visible: draft!.agentVisible });
    if (epoch.current !== revision) return;
    clear();
    await refresh();
  });
  const remove = (id: string) => operate(async revision => {
    await request("delete", { id });
    if (epoch.current !== revision) return;
    if (draft?.id === id) clear();
    setDeleting(null);
    await refresh();
  });
  return { records, draft, error, listError, loading, busy: busy || describing, fingerprints, loadSSH, scan, deleting, setDeleting, refresh, begin, update, clear, reveal, save, remove };
}
