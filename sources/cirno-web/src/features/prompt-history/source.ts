/** A conversation owns one bounded page cache shared by its rail and search list. */
import type { PromptPage } from "@/lib/contracts/history";
import { PROMPT_PAGE_SIZE, type PromptPageOptions } from "@/lib/api/prompt-directory";

interface CachedPage { query: string; page: PromptPage }
interface Failure { message: string; offset?: number }
interface Pending { query: string; controller: AbortController; epoch: number }
export interface DirectorySnapshot {
  count: number;
  revision: string | null;
  pages: ReadonlyMap<string, CachedPage>;
  totals: ReadonlyMap<string, number>;
  failures: ReadonlyMap<string, Failure>;
  loading: ReadonlySet<string>;
}
export const EMPTY_DIRECTORY: DirectorySnapshot = {
  count: 0, revision: null, pages: new Map(), totals: new Map(), failures: new Map(), loading: new Set(),
};
const MAX_CACHED_PAGES = 12;
type LoadPage = (options: PromptPageOptions, signal: AbortSignal) => Promise<PromptPage>;

export class PromptDirectorySource {
  private pages = new Map<string, CachedPage>();
  private totals = new Map<string, number>();
  private failures = new Map<string, Failure>();
  private pending = new Map<string, Pending>();
  private listeners = new Set<() => void>();
  private epoch = 0;
  private snapshot = EMPTY_DIRECTORY;

  constructor(private readonly fetchPage: LoadPage) {}

  getSnapshot = (): DirectorySnapshot => this.snapshot;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  private publish(count = this.snapshot.count, revision = this.snapshot.revision): void {
    this.snapshot = { count, revision, pages: new Map(this.pages), totals: new Map(this.totals),
      failures: new Map(this.failures), loading: new Set([...this.pending.values()].map((item) => item.query)) };
    this.listeners.forEach((listener) => listener());
  }

  cancel = (): void => {
    this.epoch += 1;
    this.pending.forEach((request) => request.controller.abort());
    this.pending.clear();
  };

  refresh = (): void => {
    this.cancel();
    this.failures.clear();
    void this.load("", undefined);
  };

  retry = (query: string): void => {
    const failed = this.failures.get(query);
    this.failures.delete(query);
    void this.load(query, failed?.offset);
  };

  ensure = (query: string, start: number, end: number): void => {
    if (this.failures.has(query)) return;
    const total = this.totals.get(query);
    if (total === undefined) {
      // A search starts at the first match; the initial unfiltered load selects the tail.
      if (query) void this.load(query, 0);
      return;
    }
    const stop = Math.min(end, total);
    for (let offset = Math.floor(Math.max(0, start) / PROMPT_PAGE_SIZE) * PROMPT_PAGE_SIZE; offset < stop; offset += PROMPT_PAGE_SIZE) {
      let covered = true;
      for (let index = offset; index < Math.min(offset + PROMPT_PAGE_SIZE, stop); index += 1) {
        if (![...this.pages.values()].some((entry) => entry.query === query && index >= entry.page.offset
          && index < entry.page.offset + entry.page.prompts.length)) { covered = false; break; }
      }
      if (!covered) void this.load(query, offset);
    }
  };

  private async load(query: string, offset: number | undefined): Promise<void> {
    if (query) {
      for (const [key, other] of this.pending) if (other.query && other.query !== query) {
        other.controller.abort(); this.pending.delete(key);
      }
      for (const term of this.failures.keys()) if (term && term !== query) this.failures.delete(term);
    }
    const identity = JSON.stringify([query, offset ?? null]);
    if (this.pending.has(identity)) return;
    const request: Pending = { query, controller: new AbortController(), epoch: this.epoch };
    this.pending.set(identity, request);
    this.publish();
    try {
      const page = await this.fetchPage({ query, offset, limit: PROMPT_PAGE_SIZE }, request.controller.signal);
      if (request.epoch !== this.epoch || request.controller.signal.aborted) return;
      if (page.revision === null) throw new Error("History changed while loading navigation; retry.");
      if (page.revision !== this.snapshot.revision) {
        // Results from a previous revision cannot overwrite a newer directory.
        this.epoch += 1;
        this.pending.forEach((other) => { if (other !== request) other.controller.abort(); });
        this.pending.clear();
        this.pages.clear();
        this.totals.clear();
        this.failures.clear();
      }
      this.totals.set("", page.count);
      this.totals.set(query, page.total);
      // Retain only the current search and normal navigation metadata.
      for (const term of this.totals.keys()) if (query && term && term !== query) this.totals.delete(term);
      const cacheKey = JSON.stringify([query, page.offset]);
      this.pages.delete(cacheKey);
      this.pages.set(cacheKey, { query, page });
      while (this.pages.size > MAX_CACHED_PAGES) this.pages.delete(this.pages.keys().next().value!);
      this.failures.delete(query);
      this.pending.delete(identity);
      this.publish(page.count, page.revision);
      if (query && ![...this.pages.values()].some((entry) => !entry.query)) void this.load("", undefined);
    } catch (cause) {
      if (request.epoch !== this.epoch || request.controller.signal.aborted) return;
      this.failures.set(query, { message: cause instanceof Error ? cause.message : String(cause), offset });
    } finally {
      if (this.pending.get(identity) === request) {
        this.pending.delete(identity);
        this.publish();
      }
    }
  }
}
