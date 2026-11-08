import type { ComposerDraft, DraftStorageIssue } from "./contracts";
import { sameComposerDraft } from "./identity";
import { readDraft, saveDraft, STORAGE_PREFIX } from "./persistence";

/** Memory owns the current revision; persistence failures never evict that revision. */
export class ComposerDraftStore extends Map<string, ComposerDraft> {
  private loaded = new Set<string>();
  private persistent = new Map<string, boolean>();
  private issues = new Map<string, DraftStorageIssue>();
  private listeners = new Map<string, Set<() => void>>();
  constructor(entries?: Iterable<readonly [string, ComposerDraft]>) {
    super();
    for (const [key, draft] of entries ?? []) super.set(key, draft);
  }
  getStorageIssue = (key: string) => this.issues.get(key) ?? null;
  subscribeStorage = (key: string, listener: () => void) => {
    const group = this.listeners.get(key) ?? new Set();
    group.add(listener);
    this.listeners.set(key, group);
    return () => { group.delete(listener); if (!group.size) this.listeners.delete(key); };
  };
  private report(key: string, issue: DraftStorageIssue | null) {
    const previous = this.issues.get(key);
    if (previous?.action === issue?.action && previous?.detail === issue?.detail) return;
    if (issue) this.issues.set(key, issue); else this.issues.delete(key);
    // Reads can initialize a composer during render. Subscribers observe the
    // current issue after that render rather than receiving a render-time write.
    queueMicrotask(() => { for (const listener of this.listeners.get(key) ?? []) listener(); });
  }
  private attempt(key: string, action: DraftStorageIssue["action"], operation: () => void) {
    try { operation(); this.report(key, null); }
    catch (error) { this.report(key, { action, detail: error instanceof Error ? error.message : String(error) }); }
  }
  override get(key: string, persist = false): ComposerDraft | undefined {
    if (super.has(key) || !persist || this.loaded.has(key)) return super.get(key);
    this.loaded.add(key);
    this.persistent.set(key, true);
    this.attempt(key, "read", () => {
      const raw = localStorage.getItem(STORAGE_PREFIX + key);
      const draft = raw ? readDraft(raw) : undefined;
      if (draft) super.set(key, draft);
    });
    return super.get(key);
  }
  override set(key: string, draft: ComposerDraft, persist = false): this {
    const previous = super.get(key);
    super.set(key, previous && sameComposerDraft(previous, draft) ? previous : draft);
    this.loaded.add(key);
    this.persistent.set(key, persist);
    if (persist) this.attempt(key, "save", () => saveDraft(key, draft));
    return this;
  }
  override delete(key: string, persist = this.persistent.get(key) ?? true): boolean {
    const deleted = super.delete(key);
    this.loaded.add(key);
    if (persist)
      this.attempt(key, "remove", () => localStorage.removeItem(STORAGE_PREFIX + key));
    return deleted;
  }
  retryStorage = (key: string): ComposerDraft | undefined => {
    const issue = this.issues.get(key);
    if (!issue) return;
    if (issue.action === "read") {
      this.loaded.delete(key);
      return this.get(key, true);
    }
    const draft = super.get(key);
    this.attempt(key, issue.action, () => {
      if (draft) saveDraft(key, draft);
      else localStorage.removeItem(STORAGE_PREFIX + key);
    });
  };
}
