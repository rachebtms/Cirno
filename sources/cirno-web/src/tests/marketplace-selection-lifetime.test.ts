import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useMarketplaceInstall } from "@/features/skills/model/useMarketplaceInstall";
import { useMarketplaceSearch } from "@/features/skills/model/useMarketplaceSearch";
import type { SkillService } from "@/features/skills/model/service";
import type { MarketplaceSkillSummary } from "@/lib/contracts/skills";

function skill(name: string): MarketplaceSkillSummary {
  return { id: `team/research/${name}`, skill_id: name, name, provider: "skills_sh", source: "team/research", installs: 0, url: "https://skills.sh", installed: false, install_supported: true, metric: "installs_total" };
}
function service(): SkillService {
  return {
    read: vi.fn(), update: vi.fn(), remove: vi.fn(),
    search: vi.fn<SkillService["search"]>(async query => ({ query, skills: [skill(query)], provider: "all", install_supported: true })),
    popular: vi.fn<SkillService["popular"]>(async () => ({ skills: [], period: "mixed", provider: "all", install_supported: true })),
    trends: vi.fn(async () => ({ trends: {} })),
    install: vi.fn(async () => ({ skills: [], last_action: { name: "first", installed: true, already_installed: false } })),
  };
}
afterEach(() => vi.useRealTimers());
it.each(["select", "close"])("ignores a retired installation %s callback", action => {
  const first = service(), next = service();
  const view = renderHook(useMarketplaceInstall, { initialProps: first });
  act(() => view.result.current.select(skill("old")));
  const old = view.result.current;
  view.rerender(next);
  act(() => view.result.current.select(skill("current")));
  act(() => action === "select" ? old.select(skill("stale")) : old.close());
  expect(view.result.current.selected?.name).toBe("current");
});
it.each(["change", "close"])("does not submit an earlier confirmation after selection %s", async action => {
  const api = service(), view = renderHook(useMarketplaceInstall, { initialProps: api });
  act(() => view.result.current.select(skill("first")));
  const confirm = view.result.current.install;
  act(() => action === "change" ? view.result.current.select(skill("second")) : view.result.current.close());
  await act(async () => { await confirm(); });
  expect(api.install).not.toHaveBeenCalled();
});
it("keeps an accepted installation locked before React publishes the busy state", async () => {
  let finish!: (value: Awaited<ReturnType<SkillService["install"]>>) => void;
  const api = service();
  vi.mocked(api.install).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const view = renderHook(useMarketplaceInstall, { initialProps: api });
  act(() => view.result.current.select(skill("first")));
  const controls = view.result.current;
  let pending!: unknown;
  act(() => { pending = controls.install(); controls.close(); controls.select(skill("second")); });
  expect(view.result.current.selected?.name).toBe("first");
  expect(api.install).toHaveBeenCalledExactlyOnceWith(skill("first"));
  await act(async () => { finish({ skills: [], last_action: { name: "first", installed: true, already_installed: false } }); await pending; });
  expect(view.result.current.selected).toBeNull();
});
it("does not revive an installation selection after leaving and returning to a service", () => {
  const api = service(), view = renderHook(useMarketplaceInstall, { initialProps: api });
  act(() => view.result.current.select(skill("first")));
  view.rerender(service());
  view.rerender(api);
  expect(view.result.current.selected).toBeNull();
});
it("retains a failed installation selection and releases the gate for explicit retry", async () => {
  const api = service(), view = renderHook(useMarketplaceInstall, { initialProps: api });
  vi.mocked(api.install).mockRejectedValueOnce(new Error("installation failed"));
  act(() => view.result.current.select(skill("first")));
  await act(() => view.result.current.install());
  expect(view.result.current.selected?.name).toBe("first");
  expect(view.result.current.operation.error).toBe("installation failed");
  expect(view.result.current.operation.busy).toBe(false);
  await act(() => view.result.current.install());
  expect(api.install).toHaveBeenCalledTimes(2);
  expect(view.result.current.selected).toBeNull();
});
it("does not revive a prior search draft and result after leaving and returning to a service", async () => {
  const api = service(), view = renderHook(useMarketplaceSearch, { initialProps: api });
  act(() => view.result.current.change("first"));
  await act(() => view.result.current.retrySearch());
  await waitFor(() => expect(view.result.current.snapshot?.query).toBe("first"));
  view.rerender(service());
  view.rerender(api);
  expect(view.result.current.query).toBe("");
  expect(view.result.current.snapshot).toBeNull();
});
it("does not let a retired draft setter overwrite the replacement search", () => {
  const api = service(), view = renderHook(useMarketplaceSearch, { initialProps: api });
  const change = view.result.current.change;
  view.rerender(service());
  act(() => view.result.current.change("current"));
  act(() => change("stale"));
  expect(view.result.current.query).toBe("current");
});
it("retains same-owner loaded results and does not refetch on ordinary rerenders", async () => {
  const api = service(), view = renderHook(useMarketplaceSearch, { initialProps: api });
  act(() => view.result.current.change("current"));
  await act(() => view.result.current.retrySearch());
  await waitFor(() => expect(view.result.current.snapshot?.query).toBe("current"));
  view.rerender(api);
  expect(view.result.current.query).toBe("current");
  expect(view.result.current.snapshot?.query).toBe("current");
  expect(api.search).toHaveBeenCalledTimes(1);
  expect(api.popular).toHaveBeenCalledTimes(1);
});
it("does not let a retired explicit search cancel the new query's debounce", async () => {
  vi.useFakeTimers();
  const api = service(), view = renderHook(useMarketplaceSearch, { initialProps: api });
  act(() => view.result.current.change("first"));
  const retry = view.result.current.retrySearch;
  act(() => view.result.current.change("second"));
  await act(async () => { await retry(); await vi.advanceTimersByTimeAsync(350); });
  expect(api.search).toHaveBeenCalledExactlyOnceWith("second");
});
