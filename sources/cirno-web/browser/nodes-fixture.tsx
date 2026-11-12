import { useMemo, useState } from "react";
import { Button } from "@heroui/react";
import type { CirnoClient } from "@/lib/cirno-client";
import type { CredentialInfo, SSHResponse } from "@/features/credentials/model/contracts";
import { CredentialsTab } from "@/features/credentials/CredentialsTab";
import { NodesSettings } from "@/features/settings/nodes/NodesSettings";
import { useTheme } from "@/hooks/useTheme";

export function NodesFixture() {
  useTheme();
  const [view, setView] = useState("nodes");
  const client = useMemo(() => {
    let failSave = true, failCredential = true;
    let jobSettings = { poll_interval_seconds: 60, retention_days: 30 }, jobReads = 0;
    const showJobs = new URLSearchParams(location.search).has("jobs");
    let records: CredentialInfo[] = [
      { id: "research", label: "Research Node", kind: "ssh", agent_visible: true },
      { id: "available", label: "Available SSH", kind: "ssh", agent_visible: false },
    ];
    const connections = new Map<string, SSHResponse>(records.map(record => [record.id, {
      host: "research.example", port: 22, username: "owner", auth_method: "key", password: "", identity_file: "",
      working_directory: "/research", host_key: "", node_enabled: record.id === "research",
    }]));
    const metadata = () => records.map(record => ({ ...record, node_enabled: connections.get(record.id)?.node_enabled ?? false }));
    const nodes = () => records.flatMap(record => {
      const connection = connections.get(record.id);
      if (!connection?.node_enabled) return [];
      const { password, ...fields } = connection;
      return [{ ...fields, id: record.id, name: record.label, agent_visible: record.agent_visible, has_password: !!password }];
    });
    return { requestMutation: async (_name: string, payload: { action: string; values: Record<string, unknown> }) => {
      const { action, values } = payload, id = String(values.id ?? "");
      if (action === "credentials.list") return { records: metadata() };
      if (action === "credentials.describe" || action === "credentials.reveal") {
        const connection = connections.get(id)!;
        if (action === "credentials.reveal") return { ssh: { ...connection } };
        const { password, ...fields } = connection;
        return { ssh: { ...fields, has_password: !!password } };
      }
      if (action === "credentials.save") {
        if (failCredential) { failCredential = false; throw new Error("Fixture credential save failed"); }
        const saved = { id: id || "gpu", label: String(values.label), kind: values.kind, agent_visible: values.agent_visible } as CredentialInfo;
        records = [...records.filter(row => row.id !== saved.id), saved];
        const connection = values.ssh as SSHResponse;
        connections.set(saved.id, { ...connection, password: connection.password || connections.get(saved.id)?.password || "",
          node_enabled: !!values.node_enabled, working_directory: String(values.working_directory) });
        return saved;
      }
      if (action === "credentials.delete") { records = records.filter(row => row.id !== id); connections.delete(id); return { ok: true }; }
      if (action === "nodes.list") return { nodes: nodes(), job_settings: jobSettings, jobs: showJobs ? [{
        id: "research-job", node_id: "research", command: "python train.py --dataset research", output: "Baseline checked.",
        state: ++jobReads === 1 ? "running" : "completed", checked_at: "2026-11-12T08:00:00Z",
        ...(jobReads > 1 ? { finished_at: "2026-11-12T08:00:10Z" } : {}),
      }] : [] };
      if (action === "nodes.settings.save") { jobSettings = { ...jobSettings, ...values }; return { job_settings: jobSettings }; }
      if (action === "nodes.save") {
        if (failSave) { failSave = false; throw new Error("Fixture Node save failed"); }
        const connection = connections.get(id || String(values.credential_id))!;
        connection.node_enabled = true; connection.working_directory = String(values.working_directory);
        connection.init_script = String(values.init_script ?? ""); connection.environment = values.environment as Record<string, string>;
        return { nodes: nodes() };
      }
      if (action === "nodes.execute") return values.command === "ssh-keygen -lf missing"
        ? { output: "missing: No such file or directory", stdout: "", stderr: "missing: No such file or directory", exit_code: 2 }
        : { output: values.command === "true" ? "" : "Linux research-node\nCPU load: 0.04\n", exit_code: 0 };
      if (action === "nodes.test") return { output: "SSH connection succeeded" };
      if (action === "nodes.scan") return { host_key: "fixture-host ssh-ed25519 fixture-key", fingerprints: "SHA256:fixture-host-key" };
      if (action === "nodes.delete") { connections.get(id)!.node_enabled = false; return { ok: true }; }
      throw new Error(`Unexpected Node action: ${action}`);
    } } as unknown as CirnoClient;
  }, []);
  return <main className="min-h-screen bg-background p-4 text-foreground sm:p-8"><div className="mx-auto max-w-4xl">
    <div className="mb-5 flex gap-2"><Button variant="secondary" onPress={() => setView("nodes")}>Manage Nodes</Button>
      <Button variant="secondary" onPress={() => setView("credentials")}>Manage credentials</Button></div>
    {view === "nodes" ? <><h1 className="mb-5 text-xl font-semibold">Nodes</h1><NodesSettings client={client} /></> : <CredentialsTab client={client} active />}
  </div></main>;
}
