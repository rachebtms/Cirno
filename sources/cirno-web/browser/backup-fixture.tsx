import { useState } from "react";
import { BackupSettings } from "@/components/settings/system/BackupSettings";
import { AgentActivityCluster } from "@/components/thread/AgentActivityCluster";
import { CirnoClient } from "@/lib/cirno-client";

const client = new CirnoClient({ url: "ws://localhost:1", reconnect: false });
const workspace = "/workspaces/research/long-term-experiment-and-evidence";
client.backupRequest = async <T,>(action: string): Promise<T> => {
  if (action === "catalog") return { instance: "/data/cirno", selected: [workspace], pending_restore: false, recommended: [
    { path: "/data/cirno/state/cli/config/tea", kind: "tools", included: true, directory: true },
    { path: workspace, kind: "workspace", included: false, directory: true },
    { path: "/home/owner/.config/gh", kind: "tools", included: false, directory: true },
  ] } as T;
  if (action === "upload") return { id: "preview", version: "0.1.4", created_at: "2026-11-03T00:00:00Z", instance: "/original/cirno", extras: [{ path: workspace, archive: "extras/0", directory: true }] } as T;
  return { ok: true } as T;
};
const event = { phase: "end" as const, call_id: "node", name: "nodes__execute", arguments: { node_id: "lab", command: "cd /srv/research\npython experiment.py --seed 42\nprintf 'finished'" }, result: "epoch 1\nepoch 2\nfinished" };

export function BackupFixture() {
  const [restarted, setRestarted] = useState(false);
  return <main className="mx-auto max-w-3xl px-4 py-6">
    <BackupSettings client={client} onRestart={() => { setRestarted(true); }} />
    <output aria-label="Restarted">{String(restarted)}</output>
    <section aria-label="Node execution" className="mt-8"><AgentActivityCluster expanded messages={[{ id: "node", role: "tool", kind: "trace", content: "", traces: [`nodes__execute(${JSON.stringify(event.arguments)})`], createdAt: 1, toolEvents: [event] }]} isTurnStreaming={false} hasBodyBelow={false} /></section>
  </main>;
}
