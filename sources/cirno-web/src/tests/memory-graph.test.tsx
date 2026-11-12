import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MemoryRecord } from "@/lib/contracts/memory";
import type { WebUIMutationTransport } from "@/lib/api";
import { MemoryTab } from "@/features/memory/MemoryTab";
import { memoryCloud } from "@/features/memory/model/cloud";
import { workspacePanels } from "@/features/workbench/modules";
import { panelTabIdentity } from "@/features/workbench/model/tab-policy";
import { MemorySettings } from "@/features/memory/MemorySettings";
import { WorkspaceOpenContext } from "@/features/workbench/context";

vi.mock("@/features/memory/ui/MemoryCloud", () => ({
  MemoryCloud: ({ records }: { records: MemoryRecord[] }) => <output data-testid="graph-ids">{records.map(row => row.id).join(",")}</output>,
}));
const row: MemoryRecord = { id: "one", title: "Measured fact", source: "test", layer: "knowledge", kind: "fact", revision: 1, scope: "user", status: "active", tags: ["calibration"], updated_at: "2026-11-10T00:00:00Z" };

describe("memory cloud", () => {
  it("keeps index maintenance in settings and opens search in the Memory tab", async () => {
    const open = vi.fn();
    const requestMutation = vi.fn(async () => ({ counts: {}, pending: 0, failed: 0, index_bytes: 0, last_dream: null }));
    render(<WorkspaceOpenContext.Provider value={open}><MemorySettings client={{ requestMutation } as WebUIMutationTransport} /></WorkspaceOpenContext.Provider>);
    fireEvent.click(screen.getByRole("button", { name: "Open Memory" }));
    expect(open).toHaveBeenCalledWith("memory", { sessionKey: null });
    await waitFor(() => expect(requestMutation).toHaveBeenCalledWith("instance.action", { action: "memory.status" }));
    expect(screen.queryByRole("textbox", { name: "Search memories" })).not.toBeInTheDocument();
    expect(requestMutation).toHaveBeenCalledTimes(1);
  });
  it("shows actual directed relations and shared tags, excluding endpoints outside the page", () => {
    const model = memoryCloud([row, { ...row, id: "two", tags: ["calibration", "unique"] }], [
      { source: "one", target: "two", relation: "supports" },
      { source: "one", target: "private", relation: "related" },
    ]);
    expect(model.nodes.map(node => node.id)).toEqual(["one", "two", "tag:calibration"]);
    expect(model.links).toEqual([
      { source: "one", target: "two", relation: "supports" },
      { source: "one", target: "tag:calibration", relation: "tag" },
      { source: "two", target: "tag:calibration", relation: "tag" },
    ]);
  });
  it("bounds tag hubs even on a large, heavily tagged collection", () => {
    const records = Array.from({ length: 300 }, (_, i) => ({ ...row, id: `row-${i}`, tags: Array.from({ length: 20 }, (_, j) => `tag-${Math.floor(i / 2)}-${j}`) }));
    const model = memoryCloud(records, []);
    expect(model.nodes.filter(node => node.tag)).toHaveLength(60);
    expect(model.nodes.filter(node => node.memory)).toHaveLength(300);
  });
  it("uses one singleton tab regardless of the launching conversation", () => {
    expect(workspacePanels.get("memory").showInMenu).toBe(true);
    const tab = { id: "a", type: "memory" as const, sessionKey: "a" };
    expect(panelTabIdentity(tab, workspacePanels)).toBe(panelTabIdentity({ ...tab, id: "b", sessionKey: "b" }, workspacePanels));
  });
  it("paginates the applied search and resets the graph for a new search", async () => {
    const requestMutation = vi.fn(async (_method: string, { action, values }: { action: string; values: Record<string, unknown> }) => {
      if (action !== "memory.graph") throw new Error(`Unexpected ${action}`);
      return { memories: [{ ...row, id: values.query ? "match" : values.offset ? "two" : "one" }],
        links: [], has_more: !values.offset && !values.query, next_offset: values.offset ? 31 : 30 };
    });
    render(<MemoryTab client={{ requestMutation } as WebUIMutationTransport} active />);
    await waitFor(() => expect(screen.getByTestId("graph-ids")).toHaveTextContent("one"));
    fireEvent.change(screen.getByRole("textbox", { name: "Search memories" }), { target: { value: "not yet applied" } });
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(screen.getByTestId("graph-ids")).toHaveTextContent("one,two"));
    expect(requestMutation).toHaveBeenLastCalledWith("instance.action", expect.objectContaining({
      action: "memory.graph", values: expect.objectContaining({ query: "", offset: 30, ids: ["one"] }),
    }));
    fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
    await waitFor(() => expect(screen.getByTestId("graph-ids")).toHaveTextContent(/^match$/));
    expect(requestMutation).toHaveBeenLastCalledWith("instance.action", expect.objectContaining({ values: expect.objectContaining({ query: "not yet applied", offset: 0, ids: [] }) }));
  });
  it("loads all remaining pages into both the point cloud and the results list", async () => {
    const requestMutation = vi.fn(async (_method: string, { values }: { values: Record<string, unknown> }) => {
      const offset = Number(values.offset);
      return { memories: [{ ...row, id: String(offset), title: `Memory ${offset}` }], links: [],
        has_more: offset < 60, next_offset: offset + 30 };
    });
    render(<MemoryTab client={{ requestMutation } as WebUIMutationTransport} active />);
    fireEvent.click(await screen.findByRole("button", { name: "Load all" }));
    await waitFor(() => expect(screen.getByTestId("graph-ids")).toHaveTextContent("0,30,60"));
    for (const offset of [0, 30, 60]) expect(screen.getByRole("button", { name: `Memory ${offset}` })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Load all" })).not.toBeInTheDocument();
    expect(requestMutation).toHaveBeenCalledTimes(3);
  });
});
