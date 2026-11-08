import { useCallback, useEffect, useRef, useState } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import type { CredentialInfo } from "@/features/credentials/model/contracts";
import { nodeDraft, type NodeDraft, type NodeJob, type NodeRecord } from "./contracts";

export function useNodes(client: CirnoClient) {
  const [nodes, setNodes] = useState<NodeRecord[]>([]), [jobs, setJobs] = useState<NodeJob[]>([]);
  const [credentials, setCredentials] = useState<CredentialInfo[]>([]);
  const [draft, setDraft] = useState<NodeDraft | null>(null);
  const [target, setTarget] = useState<NodeRecord | null>(null);
  const [command, setCommand] = useState(""), [output, setOutput] = useState<string | null>(null);
  const [notice, setNotice] = useState(""), [error, setError] = useState(""), [listError, setListError] = useState("");
  const [operation, setOperation] = useState<string | null>(null), [loading, setLoading] = useState(true);
  const generation = useRef(0), listing = useRef(0), locked = useRef(false);
  const request = useCallback(<T,>(action: string, values: object = {}) => client.requestMutation<T>(
    "instance.action", { action, values }, action === "nodes.execute" ? 130_000 : 30_000), [client]);
  const refresh = useCallback(async () => {
    const ticket = ++listing.current;
    setLoading(true);
    try {
      const [body, vault] = await Promise.all([
        request<{ nodes: NodeRecord[]; jobs: NodeJob[] }>("nodes.list"),
        client.requestMutation<{ records: CredentialInfo[] }>("workbench.action", { action: "credentials.list", values: {} }),
      ]);
      if (ticket === listing.current) { setNodes(body.nodes); setCredentials(vault.records.filter(record => record.kind === "ssh")); setJobs(body.jobs); setListError(""); }
    } catch (reason) { if (ticket === listing.current) setListError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (ticket === listing.current) setLoading(false); }
  }, [client, request]);
  useEffect(() => {
    setNodes([]); setJobs([]); setDraft(null); setTarget(null); setCommand(""); setOutput(null); setNotice(""); setError("");
    void refresh();
    return () => { generation.current++; listing.current++; };
  }, [refresh]);
  async function perform<T>(name: string, values: object, accept: (body: T) => void, reload = false) {
    if (locked.current) return;
    locked.current = true; setOperation(name); setError(""); setNotice("");
    const ticket = generation.current;
    try {
      const body = await request<T>(name, values);
      if (ticket !== generation.current) return;
      accept(body);
      if (reload) await refresh();
    } catch (reason) { if (ticket === generation.current) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { locked.current = false; setOperation(null); }
  }
  const edit = (node?: NodeRecord) => { setDraft(nodeDraft(node)); setError(""); setNotice(""); };
  const startCommand = (node: NodeRecord) => { setTarget(node); setCommand(""); setOutput(null); setError(""); setNotice(""); };
  const save = () => perform("nodes.save", { ...draft! }, () => setDraft(null), true);
  const test = (node: NodeRecord) => perform<{ output: string }>("nodes.test", { id: node.id }, body => setNotice(body.output));
  const execute = () => {
    setOutput(null);
    return perform<{ output: string }>("nodes.execute", { id: target!.id, command }, body => setOutput(body.output));
  };
  const remove = (node: NodeRecord) => perform("nodes.delete", { id: node.id }, () => {
    if (draft?.id === node.id) setDraft(null);
    if (target?.id === node.id) setTarget(null);
  }, true);
  const readJob = (job: NodeJob) => perform("nodes.job", { id: job.id }, () => {}, true);
  const stopJob = (job: NodeJob) => perform("nodes.stop", { id: job.id }, () => {}, true);
  return { nodes, credentials, jobs, loading, listError, error, notice, operation, busy: operation !== null,
    draft, setDraft, target, setTarget, command, setCommand, output, refresh, edit, startCommand, save, test, execute, remove, readJob, stopJob };
}
export type NodesController = ReturnType<typeof useNodes>;
