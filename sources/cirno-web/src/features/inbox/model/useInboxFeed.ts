import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useClient } from "@/providers/ClientProvider";
import { INBOX_CATEGORIES, useInbox, type InboxCategory, type InboxNotice, type InboxPage } from "./store";
function categoryFromLocation() {
  const value = new URLSearchParams(location.hash.split("?")[1]).get("category");
  return INBOX_CATEGORIES.find(category => category === value);
}
export function useInboxFeed(onSelect: (key: string) => void, returnKey?: string | null) {
  const { t } = useTranslation();
  const { client } = useClient();
  const inbox = useInbox();
  const [category, setCategory] = useState(categoryFromLocation);
  const [page, setPage] = useState<InboxPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const categoryRef = useRef(category);
  categoryRef.current = category;
  useEffect(() => {
    const changed = () => setCategory(categoryFromLocation());
    addEventListener("hashchange", changed);
    return () => removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    if (!inbox.connected) return;
    let active = true;
    setPage(null); setError(null);
    inbox.load(category).then(page => { if (active) setPage(page); })
      .catch(reason => { if (active) setError(String(reason)); });
    return () => { active = false; };
  }, [category, inbox.connected, inbox.load]);
  useEffect(() => {
    setPage(current => {
      if (!current) return current;
      const incoming = inbox.snapshot.items.filter(notice => !category || notice.category === category);
      const updates = new Map(incoming.map(notice => [notice.id, notice]));
      const existing = new Set(current.items.map(notice => notice.id));
      return { ...current, items: [...incoming.filter(notice => !existing.has(notice.id)), ...current.items.map(notice => updates.get(notice.id) ?? notice)] };
    });
  }, [inbox.snapshot, category]);
  async function run(id: string, action: () => Promise<void>) {
    setBusy(id); setError(null);
    try { await action(); } catch (reason) { setError(String(reason)); } finally { setBusy(null); }
  }
  function selectCategory(key: string) {
    const params = new URLSearchParams(location.hash.split("?")[1]);
    if (key === "all") params.delete("category"); else params.set("category", key);
    if (returnKey) params.set("chat", returnKey);
    location.hash = "/inbox" + (params.size ? `?${params}` : "");
    setCategory(key === "all" ? undefined : key as InboxCategory);
  }
  async function markRead(ids?: string[], selectedCategory?: InboxCategory) {
    await inbox.markRead(ids, selectedCategory);
    // The shared snapshot contains only the latest page, while this view can
    // retain older pages. Apply the successful write to those rows as well.
    setPage(current => current && ({ ...current, items: current.items.map(notice =>
      (!ids || ids.includes(notice.id)) && (!selectedCategory || notice.category === selectedCategory)
        ? { ...notice, read_at: notice.read_at ?? Date.now() } : notice) }));
  }
  const open = (notice: InboxNotice) => run(notice.id, async () => {
    const target = await client.requestMutation<{ session_key: string | null }>("instance.action", { action: "inbox.open", values: { id: notice.id } });
    await markRead([notice.id]);
    if (!target.session_key) throw new Error(t("inbox.conversationUnavailable"));
    onSelect(target.session_key);
  });
  const decide = (notice: InboxNotice, approved: boolean) => run(notice.id, async () => {
    await client.requestMutation("instance.action", { action: "approvals.decide", values: { id: notice.data.approval_id, approved } });
    await inbox.refresh();
  });
  const more = () => run("more", async () => {
    const before = page?.next_before;
    if (!before) return;
    const requested = category;
    const next = await inbox.load(requested, before);
    if (requested !== categoryRef.current) return;
    setPage(current => {
      if (!current) return current;
      const existing = new Set(current.items.map(notice => notice.id));
      return { ...next, items: [...current.items, ...next.items.filter(notice => !existing.has(notice.id))] };
    });
  });
  const refresh = () => run("refresh", async () => {
    const requested = category;
    const [, next] = await Promise.all([inbox.refresh(), inbox.load(requested)]);
    if (requested === categoryRef.current) setPage(next);
  });
  return { page, category, busy, error: error ?? inbox.error, unread: inbox.snapshot.unread, selectCategory, open, decide, more,
    refresh, markRead: (notice: InboxNotice) => run(notice.id, () => markRead([notice.id])),
    markAllRead: () => run("read", () => markRead(undefined, category)) };
}
export type InboxFeed = ReturnType<typeof useInboxFeed>;
