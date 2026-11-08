import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  useMarketplaceSearch,
  useMarketplaceTrends,
} from "@/features/skills/model/useMarketplaceSearch";
import { useSkillDetail } from "@/features/skills/model/useSkillDetail";
import { useMarketplaceInstall } from "@/features/skills/model/useMarketplaceInstall";
import type { SkillService } from "@/features/skills/model/service";
import type {
  SkillDetail,
  MarketplaceSkillSummary,
  SkillsSearchPayload,
  SkillsTrendingPayload,
} from "@/lib/contracts/skills";
import { SKILLS_CHANGED_EVENT } from "@/lib/skill-events";
const detail: SkillDetail = {
  name: "research",
  source: "home",
  description: "Research",
  available: true,
  enabled: true,
  raw_markdown: "Exact instructions",
  requirements: null,
};
const market: MarketplaceSkillSummary = {
  id: "skills_sh:research",
  skill_id: "research",
  name: "Research",
  source: "team/research",
  provider: "skills_sh",
  installs: 123,
  url: "https://skills.sh/team/research",
  installed: false,
  install_supported: true,
  metric: "installs_total",
};
const response = (query: string): SkillsSearchPayload => ({
  query,
  skills: [],
  provider: "all",
  install_supported: true,
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function service(patch: Partial<SkillService> = {}): SkillService {
  return {
    read: vi.fn(async () => detail),
    update: vi.fn(async () => ({
      skills: [{ ...detail, enabled: false }],
      last_action: { name: detail.name, enabled: false, deleted: false },
    })),
    remove: vi.fn(async () => ({
      skills: [],
      last_action: { name: detail.name, enabled: false, deleted: true },
    })),
    popular: vi.fn(
      async (): Promise<SkillsTrendingPayload> => ({
        skills: [],
        provider: "all",
        period: "mixed",
        install_supported: true,
      }),
    ),
    search: vi.fn(async (query) => response(query)),
    trends: vi.fn(async () => ({ trends: {} })),
    install: vi.fn(async () => ({
      skills: [detail],
      last_action: {
        name: detail.name,
        installed: true,
        already_installed: false,
      },
    })),
    ...patch,
  };
}
afterEach(() => vi.useRealTimers());
it("drops an old search as soon as a newer query is typed, including its debounce period", async () => {
  vi.useFakeTimers();
  const old = deferred<SkillsSearchPayload>(),
    api = service({
      search: vi
        .fn()
        .mockImplementationOnce(() => old.promise)
        .mockResolvedValueOnce(response("second")),
    });
  const { result } = renderHook(() => useMarketplaceSearch(api));
  act(() => result.current.change("first"));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });
  act(() => result.current.change("second"));
  await act(async () => {
    old.resolve(response("first"));
  });
  expect(result.current.snapshot).toBeNull();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });
  expect(result.current.snapshot?.query).toBe("second");
});
it("submits an explicit search once instead of repeating it when the debounce expires", async () => {
  vi.useFakeTimers();
  const api = service();
  const { result } = renderHook(() => useMarketplaceSearch(api));
  act(() => result.current.change("research"));
  await act(async () => {
    await result.current.retrySearch();
    await vi.advanceTimersByTimeAsync(500);
  });
  expect(api.search).toHaveBeenCalledTimes(1);
});
it("does not silently retry a failed trend request and exposes an explicit retry", async () => {
  const api = service({
    trends: vi
      .fn()
      .mockRejectedValueOnce(new Error("Trend endpoint offline"))
      .mockResolvedValueOnce({ trends: { a: [1, 2] } }),
  });
  const { result, rerender } = renderHook(
    ({ ids }) => useMarketplaceTrends(api, ids),
    {
      initialProps: { ids: ["a"] },
    },
  );
  await waitFor(() =>
    expect(result.current.error).toBe("Trend endpoint offline"),
  );
  rerender({ ids: ["a", "a"] });
  expect(api.trends).toHaveBeenCalledTimes(1);
  await act(async () => {
    await result.current.refresh();
  });
  expect(result.current.error).toBeNull();
  expect(result.current.value?.trends.a).toEqual([1, 2]);
});
it("retains a loaded detail when an equivalent catalog summary is refreshed", async () => {
  const api = service();
  const onClose = vi.fn();
  const { result, rerender } = renderHook(
    ({ skill }) => useSkillDetail(api, skill, onClose),
    {
      initialProps: { skill: detail },
    },
  );
  await waitFor(() => expect(result.current.read.value).not.toBeNull());
  rerender({ skill: { ...detail } });
  expect(api.read).toHaveBeenCalledTimes(1);
  await act(async () => {
    await result.current.toggle();
  });
  expect(result.current.read.value?.raw_markdown).toBe("Exact instructions");
  expect(result.current.read.value?.enabled).toBe(false);
});
it("serializes detail writes and keeps a failed deletion reviewable", async () => {
  const pending = deferred<Awaited<ReturnType<SkillService["update"]>>>();
  const api = service({
    update: vi.fn(() => pending.promise),
    remove: vi
      .fn()
      .mockRejectedValue(new Error("Skill directory is read-only")),
  });
  const close = vi.fn(),
    { result } = renderHook(() => useSkillDetail(api, detail, close));
  await waitFor(() => expect(result.current.read.value).not.toBeNull());
  act(() => {
    void result.current.toggle();
    void result.current.toggle();
  });
  expect(api.update).toHaveBeenCalledTimes(1);
  await act(async () => {
    pending.resolve({
      skills: [{ ...detail, enabled: false }],
      last_action: { name: detail.name, enabled: false, deleted: false },
    });
  });
  act(() => result.current.requestDelete());
  await act(async () => {
    await result.current.remove();
  });
  expect(result.current.deleting).toBe(true);
  expect(close).not.toHaveBeenCalled();
  expect(result.current.mutation.error).toBe("Skill directory is read-only");
});
it("does not broadcast an installation acknowledgement after its account owner changes", async () => {
  const pending = deferred<Awaited<ReturnType<SkillService["install"]>>>(),
    old = service({ install: vi.fn(() => pending.promise) }),
    next = service();
  const listener = vi.fn();
  window.addEventListener(SKILLS_CHANGED_EVENT, listener);
  const { result, rerender } = renderHook(
    ({ api }) => useMarketplaceInstall(api),
    {
      initialProps: { api: old },
    },
  );
  act(() => result.current.select(market));
  act(() => {
    void result.current.install();
  });
  rerender({ api: next });
  expect(result.current.selected).toBeNull();
  expect(result.current.operation.busy).toBe(false);
  await act(async () => {
    pending.resolve({
      skills: [detail],
      last_action: {
        installed: true,
        already_installed: false,
        name: detail.name,
      },
    });
  });
  expect(listener).not.toHaveBeenCalled();
  window.removeEventListener(SKILLS_CHANGED_EVENT, listener);
});
it("does not publish a previous skill's late detail over a replacement selection", async () => {
  const pending = deferred<SkillDetail>(),
    api = service({
      read: vi
        .fn()
        .mockImplementationOnce(() => pending.promise)
        .mockResolvedValueOnce({
          ...detail,
          name: "next",
          raw_markdown: "Next instructions",
        }),
    });
  const { result, rerender } = renderHook(
    ({ skill }) => useSkillDetail(api, skill, vi.fn()),
    {
      initialProps: { skill: detail },
    },
  );
  rerender({ skill: { ...detail, name: "next" } });
  await waitFor(() => expect(result.current.read.value?.name).toBe("next"));
  await act(async () => {
    pending.resolve(detail);
  });
  expect(result.current.read.value?.raw_markdown).toBe("Next instructions");
});

it("resets validation ownership when the connected instance changes", async () => {
  const { useSkillHistory } = await import(
    "@/features/skills/model/useSkillHistory"
  );
  const pending = deferred<{
    validation: { valid: boolean; errors: string[] };
    versions: [];
  }>();
  const old = {
    requestMutation: vi.fn(() => pending.promise),
  } as unknown as import("@/lib/api").WebUIMutationTransport;
  const next = {
    requestMutation: vi.fn(),
  } as unknown as import("@/lib/api").WebUIMutationTransport;
  const { result, rerender } = renderHook(
    ({ client }) => useSkillHistory(client),
    {
      initialProps: { client: old },
    },
  );
  act(() => result.current.changeName("research"));
  act(() => {
    void result.current.validate();
  });
  expect(result.current.busy).toBe(true);
  rerender({ client: next });
  expect(result.current.name).toBe("");
  expect(result.current.busy).toBe(false);
  await act(async () => {
    pending.resolve({ validation: { valid: true, errors: [] }, versions: [] });
  });
  expect(result.current.result).toBeNull();
});
