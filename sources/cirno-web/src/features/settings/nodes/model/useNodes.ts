import { sshSessionDraft, sshSessionValues, type SSHSessionValues } from "@/components/ssh/session";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import type { CredentialInfo } from "@/features/credentials/model/contracts";
import { useNodeCatalogPolling } from "./useNodeCatalogPolling";
import { DEFAULT_NODE_JOB_SETTINGS, type NodeJobSettings, nodeDraft, type NodeDraft, type NodeJob, type NodeRecord } from "./contracts";

export function useNodes(client: CirnoClient) {
  const [ready, setReady] = useState(false);
  const [jobSettings, setJobSettings] = useState<NodeJobSettings>(DEFAULT_NODE_JOB_SETTINGS);
  const policyRevision = useRef(0), refreshing = useRef<CirnoClient | null>(null);
  const [nodes, setNodes] = useState<NodeRecord[]>([]), [jobs, setJobs] = useState<NodeJob[]>([]);
  const [credentials, setCredentials] = useState<CredentialInfo[]>([]);
  const [draft, setDraft] = useState<NodeDraft | null>(null);
  const [target, setTarget] = useState<NodeRecord | null>(null);
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [command, setCommand] = useState(""), [output, setOutput] = useState<string | null>(null);
  const [notice, setNotice] = useState(""), [error, setError] = useState(""), [listError, setListError] = useState("");
  const [operation, setOperation] = useState<string | null>(null), [loading, setLoading] = useState(true);
  const [credentialReady, setCredentialReady] = useState(false);
  const generation = useRef(0), listing = useRef(0), selection = useRef(0), locked = useRef(false);
  const request = useCallback(<T,>(action: string, values: object = {}) => client.requestMutation<T>(
    "instance.action", { action, values }, ["nodes.execute", "nodes.test", "nodes.job", "nodes.stop"].includes(action) ? 130_000 : 30_000), [client]);
  const refresh = useCallback(async (quiet = false) => {
    if (refreshing.current === client) return;
    refreshing.current = client;
    const ticket = ++listing.current, policyVersion = policyRevision.current;
    if (!quiet) setLoading(true);
    try {
      const [body, vault] = await Promise.all([
        request<{ nodes: NodeRecord[]; jobs: NodeJob[]; job_settings?: NodeJobSettings }>("nodes.list"),
        client.requestMutation<{ records: CredentialInfo[] }>("workbench.action", { action: "credentials.list", values: {} }),
      ]);
      if (ticket === listing.current) { setNodes(body.nodes); setCredentials(vault.records.filter(record => record.kind === "ssh")); setJobs(body.jobs); setListError(""); setReady(true);
        if (policyVersion === policyRevision.current) setJobSettings(body.job_settings ?? DEFAULT_NODE_JOB_SETTINGS); }
    } catch (reason) { if (ticket === listing.current) setListError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (ticket === listing.current) { setLoading(false); refreshing.current = null; } }
  }, [client, request]);
  useEffect(() => {
    setReady(false); setJobSettings(DEFAULT_NODE_JOB_SETTINGS); policyRevision.current++;
    setNodes([]); setJobs([]); setDraft(null); setTarget(null); setCommand(""); setOutput(null); setExitCode(null); setNotice(""); setError("");
    void refresh();
    return () => { generation.current++; listing.current++; refreshing.current = null; };
  }, [refresh]);
  useNodeCatalogPolling(refresh);
  const saveJobSettings = async (values: Partial<NodeJobSettings>) => {
    const ticket = generation.current;
    policyRevision.current++;
    const body = await request<{ job_settings: NodeJobSettings }>("nodes.settings.save", values);
    if (ticket === generation.current) { policyRevision.current++; setJobSettings(body.job_settings); }
  };
  async function perform<T>(name: string, values: object, accept: (body: T) => void, reload = false) {
    if (locked.current) return;
    locked.current = true; setOperation(name); setError(""); setNotice("");
    const ticket = generation.current;
    try {
      const body = await request<T>(name, values);
      if (ticket !== generation.current) return;
      accept(body);
      if (reload) {
        // A catalog read begun before this mutation must not restore stale rows.
        listing.current++; refreshing.current = null;
        await refresh();
      }
    } catch (reason) { if (ticket === generation.current) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { locked.current = false; setOperation(null); }
  }
  const edit = (node?: NodeRecord) => {
    selection.current++;
    setOperation(old => old === "credentials.describe" ? null : old);
    setCredentialReady(!!node); setDraft(nodeDraft(node)); setError(""); setNotice("");
  };
  const startCommand = (node: NodeRecord) => { setTarget(node); setCommand(""); setOutput(null); setExitCode(null); setError(""); setNotice(""); };
  const save = () => {
    if (!credentialReady) return;
    try { return perform("nodes.save", { ...draft!, ...sshSessionValues(draft!) }, () => setDraft(null), true); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const selectCredential = async (id: string) => {
    const ticket = generation.current;
    const selected = ++selection.current;
    const current = () => ticket === generation.current && selected === selection.current;
    setCredentialReady(false);
    setDraft(old => old && ({ ...old, credential_id: id })); setOperation("credentials.describe"); setError("");
    try {
      const body = await client.requestMutation<{ ssh: SSHSessionValues }>("workbench.action", { action: "credentials.describe", values: { id } });
      if (current()) { setDraft(old => old?.credential_id === id ? { ...old, ...sshSessionDraft(body.ssh) } : old); setCredentialReady(true); }
    } catch (reason) { if (current()) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (current()) setOperation(null); }
  };
  const test = (node: NodeRecord) => perform<{ output: string }>("nodes.test", { id: node.id }, body => setNotice(body.output));
  const execute = () => {
    setOutput(null); setExitCode(null);
    return perform<{ output: string; exit_code?: number }>("nodes.execute", { id: target!.id, command }, body => {
      setOutput(body.output); setExitCode(body.exit_code ?? null);
    });
  };
  const remove = (node: NodeRecord) => perform("nodes.delete", { id: node.id }, () => {
    if (draft?.id === node.id) setDraft(null);
    if (target?.id === node.id) setTarget(null);
  }, true);
  const readJob = (job: NodeJob) => perform("nodes.job", { id: job.id }, () => {}, true);
  const stopJob = (job: NodeJob) => perform("nodes.stop", { id: job.id }, () => {}, true);
  return { nodes, credentials, jobs, jobSettings, saveJobSettings, ready, loading, listError, error, notice, operation, busy: operation !== null,
    draft, setDraft, credentialReady, target, setTarget, command, setCommand, output, exitCode, refresh, edit, startCommand, selectCredential, save, test, execute, remove, readJob, stopJob };
}
export type NodesController = ReturnType<typeof useNodes>;
