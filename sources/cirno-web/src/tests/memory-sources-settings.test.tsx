import userEvent from "@testing-library/user-event";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryLibrary } from "@/features/memory/MemoryLibrary";
import type { CirnoClient } from "@/lib/cirno-client";

const record = {
  id: "memory-one",
  title: "Calibration",
  source: "node://a/result#L7",
  scope: "session",
  layer: "knowledge",
  kind: "fact",
  revision: 2,
  status: "active",
  tags: ["calibration"],
  snippet: "25.125 C",
  updated_at: "2026-10-31T00:00:00Z",
};
function setup(overrides?: (action: string, values: Record<string, unknown>) => unknown) {
  const requestMutation = vi.fn(
    async (
      _method: string,
      { action, values = {} }: { action: string; values?: Record<string, unknown> },
    ) => {
      const custom = overrides?.(action, values);
      if (custom !== undefined) return custom;
      if (action === "memory.status")
        return {
          counts: { knowledge: 12 },
          pending: 2,
          failed: 1,
          index_bytes: 1048576,
          last_dream: { at: "2026-10-31T00:00:00Z", error: "Provider unavailable" },
        };
      if (action === "memory.list")
        return {
          memories: [values.offset ? { ...record, id: "memory-two", title: "Second record" } : record],
          has_more: !values.offset,
          next_offset: 10,
        };
      if (action === "memory.read")
        return {
          ...record,
          revision: values.revision ?? 2,
          content: values.revision === 1 ? "Old 30.25 C" : "Exact 25.125 C",
          links: [],
        };
      if (action === "memory.history") return { revisions: [{ ...record, revision: 1 }] };
      if (action === "memory.source")
        return {
          memory_id: "resolved-source",
          revision: 7,
          source: "memory/sources/source-one.jsonl",
          lines: [{ line: 4, text: "temperature=25.125", next_char_offset: 16000 }],
          next_line: 5,
        };
      return { scanned: 100, has_more: false };
    },
  );
  render(<MemoryLibrary client={{ requestMutation } as unknown as CirnoClient} />);
  return requestMutation;
}

describe("memory library", () => {
  it("searches explicitly and loads a bounded next page", async () => {
    const request = setup();
    expect(await screen.findByText("Calibration")).toBeVisible();
    fireEvent.change(screen.getByRole("textbox", { name: "Search memories" }), {
      target: { value: "exact threshold" },
    });
    expect(request.mock.calls.filter((call) => call[1].action === "memory.list")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith(
        "instance.action",
        expect.objectContaining({
          action: "memory.list",
          values: expect.objectContaining({ query: "exact threshold", limit: 10, offset: 0 }),
        }),
      ),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Search memories" }), {
      target: { value: "unsubmitted draft" },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Second record")).toBeVisible();
    expect(screen.getAllByText("Calibration")).toHaveLength(1);
    expect(request).toHaveBeenLastCalledWith(
      "instance.action",
      expect.objectContaining({
        action: "memory.list",
        values: expect.objectContaining({ query: "exact threshold", offset: 10 }),
      }),
    );
  });

  it("reads immutable versions and follows continuation within a long source line", async () => {
    const request = setup();
    const summary = await screen.findByText("Calibration");
    fireEvent.click(summary);
    expect(await screen.findByText("Exact 25.125 C")).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "Versions" }));
    fireEvent.click(await screen.findByRole("button", { name: "Version 1" }));
    expect(await screen.findByText("Old 30.25 C")).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "Source" }));
    expect(await screen.findByText(/4: temperature=25.125/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Next source page" }));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("instance.action", {
        action: "memory.source",
        values: { id: "resolved-source", revision: 7, start_line: 4, char_offset: 16000 },
      }),
    );
  });

  it("surfaces the failure reason and retries pending Dream work", async () => {
    const request = setup();
    expect(await screen.findByText(/Provider unavailable/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry failed Dream" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("instance.action", { action: "memory.retry" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Rebuild index" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Rebuild index" }));
    expect(await screen.findByText("Index rebuild complete")).toBeVisible();
  });

  it("keeps a backend error readable without crashing the settings page", async () => {
    setup((action) => {
      if (action === "memory.list") throw new Error("Memory database is read-only");
    });
    expect(await screen.findByText("Memory database is read-only")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Search memories" })).toBeVisible();
  });
});

it("applies the history filter immediately without requiring another search click", async () => {
  const request = setup();
  await screen.findByText("Calibration");
  fireEvent.click(screen.getByRole("switch", { name: "Include superseded records" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "instance.action",
      expect.objectContaining({
        action: "memory.list",
        values: expect.objectContaining({ include_history: true }),
      }),
    ),
  );
});

it("rebuilds successive bounded pages with a single action", async () => {
  let passes = 0;
  const request = setup((action) =>
    action === "memory.reindex" ? { scanned: 100, has_more: ++passes < 3 } : undefined,
  );
  await screen.findByText("Calibration");
  fireEvent.click(screen.getByRole("button", { name: "Rebuild index" }));
  expect(await screen.findByText("Index rebuild complete")).toBeVisible();
  expect(request.mock.calls.filter((call) => call[1].action === "memory.reindex")).toHaveLength(3);
});

it("discovers tags and applies a selected tag to the next bounded search", async () => {
  const request = setup((action) =>
    action === "memory.tags" ? { tags: [{ name: "calibration", count: 4 }] } : undefined,
  );
  await screen.findByText("Calibration");
  await userEvent.click(screen.getByRole("button", { name: "Browse tags" }));
  await userEvent.click(await screen.findByRole("button", { name: "calibration · 4" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "instance.action",
      expect.objectContaining({
        action: "memory.list",
        values: expect.objectContaining({ tags: ["calibration"] }),
      }),
    ),
  );
});

it("uses the selected retrieval mode and explains BM25 fallback", async () => {
  const request = setup((action, values) =>
    action === "memory.list"
      ? {
          memories: [record],
          has_more: false,
          next_offset: 0,
          engine: "bm25",
          warning_code: values.mode === "semantic" ? "disabled" : undefined,
        }
      : undefined,
  );
  await screen.findByText("Calibration");
  fireEvent.change(screen.getByRole("textbox", { name: "Search memories" }), {
    target: { value: "calibration" },
  });
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /Search mode$/ }));
  await user.click(await screen.findByRole("option", { name: "Vector" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      "instance.action",
      expect.objectContaining({
        action: "memory.list",
        values: expect.objectContaining({ mode: "semantic", query: "calibration", offset: 0 }),
      }),
    ),
  );
  expect(await screen.findByText("Vector retrieval is disabled; using BM25.")).toBeVisible();
  expect(screen.getByText("Used: Keyword · BM25")).toBeVisible();
});

it("shows incomplete vector coverage and the underlying fallback error", async () => {
  setup((action, values) =>
    action === "memory.list" && values.query
      ? {
          memories: [record],
          has_more: false,
          next_offset: 0,
          engine: "hybrid",
          embedding_index_pending: true,
          warning_code: "unavailable",
          warning: "Embedding worker timed out; using BM25",
        }
      : undefined,
  );
  await screen.findByText("Calibration");
  fireEvent.change(screen.getByRole("textbox", { name: "Search memories" }), {
    target: { value: "calibration" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search memories" }));
  expect(await screen.findByText(/Vector indexing is incomplete/)).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Reason" }));
  expect(screen.getByText("Embedding worker timed out; using BM25")).toBeVisible();
});

it("keeps successful search results when status inspection fails", async () => {
  setup((action) => {
    if (action === "memory.status") throw new Error("Status database unavailable");
  });
  expect(await screen.findByText("Calibration")).toBeVisible();
  expect(await screen.findByRole("alert")).toHaveTextContent("Status database unavailable");
});
