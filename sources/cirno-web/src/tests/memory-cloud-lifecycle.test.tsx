import { render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { MemoryCloud } from "@/features/memory/ui/MemoryCloud";
import type { MemoryRecord } from "@/lib/contracts/memory";

const renderer = vi.hoisted(() => {
  const methods: Record<string, ReturnType<typeof vi.fn>> = {};
  const graph: object = new Proxy({}, { get: (_target, name: string) => methods[name] ??= vi.fn(() => graph) });
  return { methods, create: vi.fn(function () { return graph; }) };
});
vi.mock("3d-force-graph", () => ({ default: renderer.create }));
const records: MemoryRecord[] = [{ id: "one", title: "Measured fact", source: "test", layer: "knowledge", kind: "fact", revision: 1, scope: "user", status: "active", tags: [], updated_at: "2026-11-10T00:00:00Z" }];
it("pauses a hidden tab, resumes on activation and disposes its renderer on close", async () => {
  const inspect = vi.fn(), tag = vi.fn();
  const { rerender, unmount } = render(<MemoryCloud records={records} active={false} onInspect={inspect} onTag={tag} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Fit to view" })).toBeEnabled());
  expect(renderer.methods.pauseAnimation).toHaveBeenCalled();
  rerender(<MemoryCloud records={records} active onInspect={inspect} onTag={tag} />);
  expect(renderer.methods.resumeAnimation).toHaveBeenCalled();
  // Selecting the graph and selecting the adjacent result share the same inspector.
  renderer.methods.onNodeClick.mock.calls[0][0]({ memory: records[0] });
  expect(inspect).toHaveBeenCalledWith(records[0]);
  unmount();
  expect(renderer.methods._destructor).toHaveBeenCalledTimes(1);
  expect(renderer.create).toHaveBeenCalledTimes(1);
});
