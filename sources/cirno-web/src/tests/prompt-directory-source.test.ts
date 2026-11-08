import { expect, it, vi } from "vitest";
import { waitFor } from "@testing-library/react";
import { PromptDirectorySource } from "@/features/prompt-history/source";
import type { PromptPage } from "@/lib/contracts/history";
import type { PromptPageOptions } from "@/lib/api/prompt-directory";

function page(offset: number, revision = "r1", count = 20000): PromptPage {
  return { offset, count, total: count, revision, prompts: Array.from({ length: Math.min(64, count - offset) }, (_, index) => ({
    id: `u${index + offset}`, index: index + offset, preview: `question ${index + offset}`,
    answerPreview: "answer", createdAt: index + 1, cursor: String(index + offset), turnId: `t${index + offset}`,
  })) };
}

it("opens a 20k-prompt directory with one small page and bounds memory across arbitrary jumps", async () => {
  const load = vi.fn<(options: PromptPageOptions, signal: AbortSignal) => Promise<PromptPage>>(async (options) => page(options.offset ?? 19936));
  const source = new PromptDirectorySource(load);
  source.refresh();
  await waitFor(() => expect(source.getSnapshot().count).toBe(20000));
  expect(load).toHaveBeenCalledTimes(1);
  expect([...source.getSnapshot().pages.values()].flatMap((entry) => entry.page.prompts)).toHaveLength(64);
  for (let index = 0; index < 30; index += 1) {
    const offset = index * 64;
    source.ensure("", offset, offset + 10);
    await waitFor(() => expect([...source.getSnapshot().pages.values()].some((entry) => entry.page.offset === offset)).toBe(true));
    expect(source.getSnapshot().pages.size).toBeLessThanOrEqual(12);
  }
  source.ensure("", 0, 1);
  await waitFor(() => expect([...source.getSnapshot().pages.values()].some((entry) => entry.page.offset === 0)).toBe(true));
  expect([...source.getSnapshot().pages.values()].flatMap((entry) => entry.page.prompts).length).toBeLessThanOrEqual(768);
  source.cancel();
});

it("a new revision discards old in-flight pages without letting a late response restore them", async () => {
  let finish!: (value: PromptPage) => void;
  const load = vi.fn<(options: PromptPageOptions, signal: AbortSignal) => Promise<PromptPage>>(async (options) => page(options.offset ?? 19936));
  const source = new PromptDirectorySource(load);
  source.refresh();
  await waitFor(() => expect(source.getSnapshot().revision).toBe("r1"));
  load.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  source.ensure("", 0, 10);
  const signal = load.mock.calls.at(-1)?.[1];
  load.mockResolvedValueOnce(page(19937, "r2", 20001));
  source.refresh();
  await waitFor(() => expect(source.getSnapshot().revision).toBe("r2"));
  finish(page(0));
  await Promise.resolve();
  expect(signal?.aborted).toBe(true);
  expect([...source.getSnapshot().pages.values()].every((entry) => entry.page.revision === "r2")).toBe(true);
  expect(source.getSnapshot().count).toBe(20001);
  source.cancel();
});

it("failed ranges stay visible and wait for explicit retry rather than making a render retry loop", async () => {
  const load = vi.fn<(options: PromptPageOptions, signal: AbortSignal) => Promise<PromptPage>>(async (options) => page(options.offset ?? 19936));
  const source = new PromptDirectorySource(load);
  source.refresh();
  await waitFor(() => expect(source.getSnapshot().revision).toBe("r1"));
  load.mockRejectedValueOnce(new Error("offline"));
  source.ensure("", 0, 1);
  await waitFor(() => expect(source.getSnapshot().failures.get("")?.message).toBe("offline"));
  for (let index = 0; index < 20; index += 1) source.ensure("", 0, 1);
  expect(load).toHaveBeenCalledTimes(2);
  expect(source.getSnapshot().pages.size).toBe(1);
  source.retry("");
  await waitFor(() => expect(source.getSnapshot().failures.size).toBe(0));
  expect(load).toHaveBeenLastCalledWith({ query: "", offset: 0, limit: 64 }, expect.any(AbortSignal));
  source.cancel();
});

it("a superseded search is cancelled and cannot replace the latest result", async () => {
  let finish!: (value: PromptPage) => void;
  const load = vi.fn<(options: PromptPageOptions, signal: AbortSignal) => Promise<PromptPage>>(async () => page(19936));
  const source = new PromptDirectorySource(load);
  source.refresh();
  await waitFor(() => expect(source.getSnapshot().revision).toBe("r1"));
  load.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  source.ensure("old", 0, 10);
  const signal = load.mock.calls.at(-1)?.[1];
  load.mockResolvedValueOnce({ ...page(0), total: 1, prompts: [page(42).prompts[0]] });
  source.ensure("new", 0, 10);
  await waitFor(() => expect(source.getSnapshot().totals.get("new")).toBe(1));
  finish({ ...page(0), total: 2, prompts: page(0).prompts.slice(0, 2) });
  await Promise.resolve();
  expect(signal?.aborted).toBe(true);
  expect(source.getSnapshot().totals.has("old")).toBe(false);
  source.cancel();
});
