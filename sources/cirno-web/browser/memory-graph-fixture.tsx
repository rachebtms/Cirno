import { useMemo, useState } from "react";
import { Workbench } from "@/features/workbench/Workbench";
import type { WorkspaceRoute } from "@/features/workbench/contracts";
import type { CirnoClient } from "@/lib/cirno-client";
import type { MemoryRecord } from "@/lib/contracts/memory";
import { useTheme } from "@/hooks/useTheme";

const records: MemoryRecord[] = Array.from({ length: Number(new URLSearchParams(location.search).get("count") ?? 72) }, (_, i) => ({
  id: `memory-${i}`, title: ["Detector calibration", "Research preference", "Experiment checkpoint", "Original measurement", "Verification result", "Paper reading method"][i % 6] + ` ${i + 1}`,
  source: `test://experiment/${i}`, scope: i % 2 ? "user" : "project", layer: ["knowledge", "profile", "task", "source", "event"][i % 5],
  kind: "fact", revision: 2, status: "active", tags: [["research", "detector"], ["preferences"], ["research", "experiments"]][i % 3],
  updated_at: "2026-11-10T00:00:00Z", snippet: "Measured temperature: 25.125 °C. The original evidence remains available.",
}));
export function MemoryGraphFixture() {
  useTheme();
  const [route, setRoute] = useState<WorkspaceRoute>({ view: "chat", activeKey: null, settingsSection: "overview" });
  const [calls, setCalls] = useState<unknown[]>([]);
  const client = useMemo(() => ({
    requestMutation: async (_method: string, { action, values = {} }: { action: string; values?: Record<string, unknown> }) => {
      setCalls(previous => [...previous, { action, values }]);
      if (action === "memory.graph") {
        const matches = records.filter(row => (!values.query || row.title.toLowerCase().includes(String(values.query).toLowerCase()))
          && (!values.scope || values.scope === "all" || row.scope === values.scope)
          && (!values.layer || values.layer === "all" || row.layer === values.layer)
          && (values.tags as string[]).every(tag => row.tags.includes(tag)));
        const offset = Number(values.offset), limit = Number(values.limit);
        const page = matches.slice(offset, offset + limit);
        const ids = new Set([...(values.ids as string[]), ...page.map(row => row.id)]);
        return { memories: page, has_more: offset + limit < matches.length, next_offset: offset + page.length, engine: "bm25",
          ...(values.mode === "semantic" ? { warning_code: "disabled" } : {}),
          links: records.slice(1).map((row, i) => ({ source: records[i].id, target: row.id, relation: "supports" }))
            .filter(link => ids.has(link.source) && ids.has(link.target)) };
      }
      if (action === "memory.read") return { ...records.find(row => row.id === values.id), content: "Exact measured temperature: 25.125 °C.", links: [] };
      if (action === "memory.history") return { revisions: [records.find(row => row.id === values.id)] };
      if (action === "memory.tags") return { tags: [{ name: "research", count: 48 }] };
      throw new Error(`Unhandled memory fixture action: ${action}`);
    },
  }) as unknown as CirnoClient, []);
  return <main style={{ height: "100dvh" }}>
    <Workbench client={client} route={route} navigationSequence={0} title="New chat" sessions={[]}
      onRoute={setRoute} onRouteVisibleChange={() => {}} onNewChat={() => {}} beforeActivate={action => action()}
      renderRoute={() => <p>Memory graph preview</p>} />
    <output hidden data-testid="memory-graph-calls">{JSON.stringify(calls)}</output>
  </main>;
}
