import type { LinkObject, NodeObject } from "3d-force-graph";
import type { MemoryLink, MemoryRecord } from "@/lib/contracts/memory";

export const MEMORY_COLORS: Record<string, string> = {
  knowledge: "#64b9b0", event: "#c9a56c", task: "#a69bd4", source: "#81a9d4", profile: "#d793ac",
};
export interface CloudNode extends NodeObject {
  id: string;
  label: string;
  color: string;
  memory?: MemoryRecord;
  tag?: string;
}
export interface CloudLink extends LinkObject<CloudNode> { relation: string }
/** Tags are explicit hubs, never invented semantic similarities. */
export function memoryCloud(records: MemoryRecord[], relations: MemoryLink[]) {
  const nodes: CloudNode[] = records.map(memory => ({
    id: memory.id, label: memory.title, color: MEMORY_COLORS[memory.layer] ?? "#81a9d4", memory,
  }));
  const ids = new Set(nodes.map(node => node.id));
  const links: CloudLink[] = relations.filter(link => ids.has(link.source) && ids.has(link.target)).map(link => ({ ...link }));
  const counts = new Map<string, number>();
  for (const memory of records) for (const tag of memory.tags) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  const hubs = new Set([...counts].filter(([, count]) => count > 1)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 60).map(([tag]) => tag));
  const tags = new Map<string, CloudNode>();
  for (const memory of records) {
    for (const tag of memory.tags) {
      if (!hubs.has(tag)) continue;
      const id = `tag:${tag}`;
      if (!tags.has(id)) tags.set(id, { id, tag, label: `#${tag}`, color: "#91a1a7" });
      links.push({ source: memory.id, target: id, relation: "tag" });
    }
  }
  return { nodes: [...nodes, ...tags.values()], links };
}
