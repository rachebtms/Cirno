import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { MemoryCloud } from "@/features/memory/ui/MemoryCloud";
import type { MemoryRecord } from "@/lib/contracts/memory";

const renderer = vi.hoisted(() => {
  const methods: Record<string, ReturnType<typeof vi.fn>> = {};
  const graph: object = new Proxy({}, { get: (_target, name: string) => methods[name] ??= vi.fn(() => graph) });
  return { methods, create: vi.fn(function () { return graph; }) };
});
vi.mock("3d-force-graph", () => ({ default: renderer.create }));
const records: MemoryRecord[] = [{ id: "one", title: "Measured fact", source: "test", layer: "knowledge", kind: "fact", revision: 1, scope: "user", status: "active", tags: [], updated_at: "2026-11-10T00:00:00Z" }];
beforeEach(() => vi.clearAllMocks());
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

it("releases each renderer when expanding and returning, keeping graph interactions", async () => {
  const inspect = vi.fn(), tag = vi.fn();
  const { unmount } = render(<MemoryCloud records={records} active onInspect={inspect} onTag={tag} />);
  await waitFor(() => expect(renderer.create).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Expand view" }));
  const dialog = await screen.findByRole("dialog", { name: "Memory cloud" });
  await waitFor(() => expect(within(dialog).getByRole("button", { name: "Fit to view" })).toBeEnabled());
  expect(renderer.create).toHaveBeenCalledTimes(2);
  expect(renderer.methods._destructor).toHaveBeenCalledTimes(1);
  const click = renderer.methods.onNodeClick.mock.calls.at(-1)![0];
  click({ memory: records[0] }); click({ tag: "research" });
  expect(inspect).toHaveBeenCalledWith(records[0]);
  expect(tag).toHaveBeenCalledWith("research");
  fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await waitFor(() => expect(renderer.create).toHaveBeenCalledTimes(3));
  expect(renderer.methods._destructor).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("button", { name: "Expand view" })).toHaveFocus();
  unmount();
  expect(renderer.methods._destructor).toHaveBeenCalledTimes(3);
});
