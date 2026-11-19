import { sshSessionDraft, sshSessionValues } from "@/components/ssh/session";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import { emptySSH, type CredentialDraft, type CredentialInfo, type CredentialPatch, type SSHResponse } from "./contracts";
import { useLifetime } from "@/ui/resources/useLifetime";

export function useCredentialVault(client: CirnoClient, active: boolean, onDirtyChange?: (dirty: boolean) => void) {
  const isCurrent = useLifetime(client);
  const stateOwner = useRef(isCurrent);
  const ownsState = stateOwner.current === isCurrent;
  const view = useRef({ client, active });
  if (view.current.client !== client || view.current.active !== active) view.current = { client, active };
  const [records, setRecords] = useState<CredentialInfo[]>([]);
  const [draft, setDraft] = useState<CredentialDraft | null>(null);
  const [error, setError] = useState("");
  const [listError, setListError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [secretVisible, setSecretVisible] = useState(false);
  const [describing, setDescribing] = useState(false), [fingerprints, setFingerprints] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);
  const epoch = useRef(0), listing = useRef(0), locked = useRef(false);
  const request = useCallback(<T,>(action: string, values = {}) =>
    client.requestMutation<T>("workbench.action", { action: `credentials.${action}`, values }), [client]);
  const fail = (reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason));
  const clear = useCallback(() => { if (!isCurrent()) return; epoch.current++; setSecretVisible(false); setDraft(null); setDescribing(false); setFingerprints(""); }, [isCurrent]);
  const refresh = useCallback(async () => {
    if (!isCurrent()) return;
    const revision = ++listing.current;
    setLoading(true);
    try {
      const body = await request<{ records: CredentialInfo[] }>("list");
      if (isCurrent() && listing.current === revision) { setRecords(body.records); setListError(""); }
    } catch (reason) { if (isCurrent() && listing.current === revision) setListError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (isCurrent() && listing.current === revision) setLoading(false); }
  }, [request, isCurrent]);
  useEffect(() => {
    stateOwner.current = isCurrent;
    locked.current = false; setBusy(false);
    clear(); setError(""); setListError(""); setDeleting(null); setRecords([]);
    return () => { listing.current++; epoch.current++; };
  }, [clear, request, isCurrent]);
  useEffect(() => { if (active) void refresh(); else setSecretVisible(false); }, [active, refresh]);
  useEffect(() => {
    onDirtyChange?.(!!draft?.modified);
    return () => onDirtyChange?.(false);
  }, [draft?.modified, onDirtyChange]);
  useEffect(() => { if (!active && draft?.id && !draft.modified) clear(); }, [active, draft, clear]);
  const begin = (record?: CredentialInfo) => {
    if (!isCurrent()) return;
    epoch.current++; setSecretVisible(false); setError(""); setDeleting(null); setFingerprints(""); setDescribing(false);
    setDraft({ id: record?.id, label: record?.label ?? "", kind: record?.kind ?? "text", username: "", value: "", modified: false, agentVisible: record?.agent_visible ?? false,
      ssh: emptySSH(), sshLoaded: !record || record.kind !== "ssh", nodeEnabled: record?.node_enabled ?? false, session: sshSessionDraft() });
    if (record?.kind === "ssh") void loadSSH(record.id);
  };
  const update = (patch: CredentialPatch) => {
    if (isCurrent()) setDraft(old => old && ({ ...old, ...patch, modified: true }));
  };
  async function operate(task: (revision: number) => Promise<void>) {
    if (!isCurrent() || !ownsState || locked.current) return;
    locked.current = true; setBusy(true); setError("");
    const revision = epoch.current;
    try { await task(revision); }
    catch (reason) { if (isCurrent() && epoch.current === revision) fail(reason); }
    finally { if (isCurrent()) { locked.current = false; setBusy(false); } }
  }
  async function loadSSH(id = draft!.id!) {
    if (!isCurrent()) return;
    const revision = epoch.current;
    setDescribing(true); setError("");
    try {
      const body = await request<{ ssh: SSHResponse }>("describe", { id });
      const { node_enabled, working_directory, init_script, environment, ...connection } = body.ssh;
      if (isCurrent() && epoch.current === revision) setDraft(old => old && ({ ...old, ssh: { ...connection, password: "", port: String(connection.port) },
        sshLoaded: true, nodeEnabled: node_enabled, session: sshSessionDraft({ working_directory, init_script, environment }) }));
    } catch (reason) { if (isCurrent() && epoch.current === revision) fail(reason); }
    finally { if (isCurrent() && epoch.current === revision) setDescribing(false); }
  }
  const scan = () => operate(async revision => {
    const body = await client.requestMutation<{ host_key: string; fingerprints: string }>("instance.action", {
      action: "nodes.scan", values: { host: draft!.ssh.host, port: Number(draft!.ssh.port) },
    });
    if (isCurrent() && epoch.current === revision) {
      setDraft(old => old && ({ ...old, ssh: { ...old.ssh, host_key: body.host_key }, modified: true }));
      setFingerprints(body.fingerprints);
    }
  });
  const reveal = () => operate(async revision => {
    const visible = view.current;
    if (!visible.active) return;
    const body = await request<{ value: string; username?: string; ssh?: SSHResponse }>("reveal", { id: draft!.id });
    if (isCurrent() && view.current === visible && epoch.current === revision) { setSecretVisible(true); setDraft(old => old && (body.ssh ? { ...old, ssh: { ...old.ssh, password: body.ssh.password } } : { ...old, value: body.value, username: body.username ?? "" })); }
  });
  const save = () => operate(async revision => {
    const { id, label, kind, value, username } = draft!;
    if (kind === "ssh") {
      const { host, port, username, auth_method, password, identity_file, host_key } = draft!.ssh;
      await request("save", { id, label, kind, ssh: { host, port: Number(port), username, auth_method, password, identity_file, host_key, init_script: draft!.session.init_script, environment: sshSessionValues(draft!.session).environment },
        node_enabled: draft!.nodeEnabled, working_directory: draft!.session.working_directory, agent_visible: draft!.agentVisible });
    } else await request("save", { id, label, kind, value, username: kind === "password" ? username : "", agent_visible: draft!.agentVisible });
    if (!isCurrent() || epoch.current !== revision) return;
    clear();
    await refresh();
  });
  const remove = (id: string) => operate(async revision => {
    await request("delete", { id });
    if (!isCurrent() || epoch.current !== revision) return;
    if (draft?.id === id) clear();
    setDeleting(null);
    await refresh();
  });
  return { secretVisible: ownsState && active && secretVisible, toggleSecret: () => { if (isCurrent() && active) setSecretVisible(value => !value); },
    records: ownsState ? records : [], draft: ownsState ? draft : null, error: ownsState ? error : "", listError: ownsState ? listError : "",
    loading: !ownsState || loading, busy: ownsState && (busy || describing), fingerprints: ownsState ? fingerprints : "", loadSSH, scan,
    deleting: ownsState ? deleting : null, setDeleting: (id: string | null) => { if (isCurrent()) setDeleting(id); }, refresh, begin, update, clear, reveal, save, remove };
}
