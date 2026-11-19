import { useContext, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useClient } from "@/providers/ClientProvider";
import { SurfaceVisibilityContext } from "@/hooks/usePageVisibility";
import { useLifetime } from "@/ui/resources/useLifetime";
import { markInboxItemsRead } from "./read-receipt";
import { INBOX_CATEGORIES, useInbox, type InboxCategory, type InboxNotice, type InboxPage } from "./store";
function categoryFromLocation() {
  const value = new URLSearchParams(location.hash.split("?")[1]).get("category");
  return INBOX_CATEGORIES.find(category => category === value);
}
export function useInboxFeed(onSelect: (key: string) => void, returnKey?: string | null) {
  const { t } = useTranslation();
  const { client } = useClient();
  const isCurrent = useLifetime(client);
  const pageOwner = useRef(isCurrent);
  const ownsPage = pageOwner.current === isCurrent;
  const inbox = useInbox();
  const visible = useContext(SurfaceVisibilityContext);
  const [category, setCategory] = useState(categoryFromLocation);
  const [page, setPage] = useState<InboxPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const viewRef = useRef({ client, category, connected: inbox.connected, visible });
  if (viewRef.current.client !== client || viewRef.current.category !== category
      || viewRef.current.connected !== inbox.connected || viewRef.current.visible !== visible) {
    viewRef.current = { client, category, connected: inbox.connected, visible };
  }
  useEffect(() => () => { viewRef.current = { ...viewRef.current }; }, []);
  const actionPending = useRef<{ owner: () => boolean } | null>(null);
  useEffect(() => {
    const changed = () => setCategory(categoryFromLocation());
    addEventListener("hashchange", changed);
    return () => removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    if (pageOwner.current !== isCurrent) setBusy(null);
    pageOwner.current = isCurrent;
    let active = true;
    setPage(null); setError(null);
    if (!inbox.connected) return;
    inbox.load(category).then(page => { if (active && isCurrent()) setPage(page); })
      .catch(reason => { if (active && isCurrent()) setError(String(reason)); });
    return () => { active = false; };
  }, [category, inbox.connected, inbox.load, isCurrent]);
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
    if (!isCurrent() || actionPending.current?.owner === isCurrent) return;
    const operation = { owner: isCurrent };
    actionPending.current = operation;
    const view = viewRef.current;
    setBusy(id); setError(null);
    try { await action(); }
    catch (reason) { if (isCurrent() && view === viewRef.current) setError(String(reason)); }
    finally { if (actionPending.current === operation) { actionPending.current = null; if (isCurrent()) setBusy(null); } }
  }
  function selectCategory(key: string) {
    const params = new URLSearchParams(location.hash.split("?")[1]);
    if (key === "all") params.delete("category"); else params.set("category", key);
    if (returnKey) params.set("chat", returnKey);
    location.hash = "/inbox" + (params.size ? `?${params}` : "");
    setCategory(key === "all" ? undefined : key as InboxCategory);
  }
  async function markRead(ids?: string[], selectedCategory?: InboxCategory) {
    const view = viewRef.current;
    const receipt = await inbox.markRead(ids, selectedCategory);
    if (!isCurrent() || receipt?.revision === undefined && view !== viewRef.current) return;
    // The shared snapshot contains only the latest page, while this view can
    // retain older pages. Apply the successful write to those rows as well.
    setPage(current => current && ({ ...current, items: markInboxItemsRead(current.items, receipt ?? { read_at: Date.now() }, ids, selectedCategory) }));
  }
  const open = (notice: InboxNotice) => run(notice.id, async () => {
    const view = viewRef.current;
    const target = await client.requestMutation<{ session_key: string | null }>("instance.action", { action: "inbox.open", values: { id: notice.id } });
    if (view !== viewRef.current) return;
    await markRead([notice.id]);
    if (view !== viewRef.current) return;
    if (!target.session_key) throw new Error(t("inbox.conversationUnavailable"));
    onSelect(target.session_key);
  });
  const decide = (notice: InboxNotice, approved: boolean) => run(notice.id, async () => {
    const view = viewRef.current;
    await client.requestMutation("instance.action", { action: "approvals.decide", values: { id: notice.data.approval_id, approved } });
    if (!isCurrent() || view !== viewRef.current) return;
    await inbox.refresh();
  });
  const more = () => run("more", async () => {
    const before = page?.next_before;
    if (!before) return;
    const view = viewRef.current;
    const next = await inbox.load(category, before);
    if (view !== viewRef.current) return;
    setPage(current => {
      if (!current) return current;
      const existing = new Set(current.items.map(notice => notice.id));
      return { ...next, items: [...current.items, ...next.items.filter(notice => !existing.has(notice.id))] };
    });
  });
  const refresh = () => run("refresh", async () => {
    const view = viewRef.current;
    const [, next] = await Promise.all([inbox.refresh(), inbox.load(category)]);
    if (view === viewRef.current) setPage(next);
  });
  return { page: ownsPage ? page : null, category, busy: ownsPage ? busy : null, error: (ownsPage ? error : null) ?? inbox.error, unread: inbox.snapshot.unread, selectCategory, open, decide, more,
    refresh, markRead: (notice: InboxNotice) => run(notice.id, () => markRead([notice.id])),
    markAllRead: () => run("read", () => markRead(undefined, category)) };
}
export type InboxFeed = ReturnType<typeof useInboxFeed>;
