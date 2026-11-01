import { useEffect, useState } from "react";
import { ArrowLeft, Bell, CheckCheck, CircleHelp, ExternalLink, Inbox, Loader2, MessageCircle, RefreshCw, Settings2, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useInbox, INBOX_CATEGORIES, type InboxCategory, type InboxNotice, type InboxPage } from "@/hooks/useInbox";
import { useClient } from "@/providers/ClientProvider";
import { runPairingAction } from "@/lib/api";
import { cn } from "@/lib/utils";

function currentCategory(): InboxCategory | undefined {
  const category = new URLSearchParams(window.location.hash.split("?")[1]).get("category");
  return INBOX_CATEGORIES.find((value) => value === category);
}

export function InboxView({ onBack, onSelect, onSettings, returnKey }: {
  onBack: () => void; onSelect: (key: string) => void; onSettings: () => void; returnKey?: string | null;
}) {
  const { t, i18n } = useTranslation();
  const { client } = useClient();
  const { snapshot, load, markRead, refresh, connected, error: inboxError } = useInbox();
  const [category, setCategory] = useState(currentCategory);
  const [page, setPage] = useState<InboxPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    const changed = () => setCategory(currentCategory());
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    if (!connected) return;
    let active = true;
    setPage(null); setError(null);
    load(category).then((next) => { if (active) setPage(next); })
      .catch((reason: Error) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [category, connected, load]);
  useEffect(() => {
    setPage((current) => {
      if (!current) return current;
      const incoming = snapshot.items.filter((item) => !category || item.category === category);
      const byId = new Map(incoming.map((item) => [item.id, item]));
      const combined = current.items.map((item) => byId.get(item.id) ?? item);
      const existing = new Set(current.items.map((item) => item.id));
      return { ...current, items: [...incoming.filter((item) => !existing.has(item.id)), ...combined] };
    });
  }, [snapshot, category]);
  async function run(id: string, action: () => Promise<void>) {
    setBusy(id); setError(null);
    try { await action(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(null); }
  }
  function changeCategory(value: string) {
    const url = new URL(window.location.href);
    const params = new URLSearchParams(url.hash.split("?")[1]);
    if (value === "all") params.delete("category"); else params.set("category", value);
    if (returnKey) params.set("chat", returnKey);
    window.location.hash = "/inbox" + (params.size ? "?" + params.toString() : "");
    setCategory(value === "all" ? undefined : value as InboxCategory);
  }
  function icon(notice: InboxNotice) {
    const Icon = notice.kind === "pairing" ? ShieldCheck : notice.category === "operations" ? CircleHelp : notice.category === "system" ? Settings2 : MessageCircle;
    return <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />;
  }
  return <section className="flex h-full min-h-0 min-w-0 flex-col bg-background" aria-label={t("inbox.title")}>
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border/40 px-4 sm:px-6">
      <Button variant="ghost" size="icon" onClick={onBack} aria-label={t("inbox.back")} className="text-muted-foreground"><ArrowLeft className="h-4 w-4" /></Button>
      <Inbox className="h-4 w-4 text-muted-foreground" /><h1 className="text-sm font-medium">{t("inbox.title")}</h1>
      <Button variant="ghost" size="icon" onClick={onSettings} aria-label={t("inbox.settings")} className="ms-auto text-muted-foreground"><Bell className="h-4 w-4" /></Button>
    </header>
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-4xl space-y-5 px-4 py-5 sm:px-8 sm:py-8">
        <nav className="overflow-x-auto pb-1" aria-label={t("inbox.categories")}>
          <SegmentedControl value={category ?? "all"} onChange={changeCategory} mode="tabs" className="w-max max-w-none" options={["all", ...INBOX_CATEGORIES].map((value) => ({ value, label: <span className="whitespace-nowrap">{t(`inbox.category.${value}`)}{value !== "all" && snapshot.unread[value as InboxCategory] > 0 ? ` · ${snapshot.unread[value as InboxCategory]}` : ""}</span> }))} />
        </nav>
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>{t("inbox.retained")}</span>
          <div className="flex shrink-0 items-center gap-1">
            <Button variant="ghost" size="icon" aria-label={t("inbox.refresh")} disabled={!!busy} onClick={() => void run("refresh", refresh)}><RefreshCw className="h-4 w-4" /></Button>
            <Button variant="ghost" size="sm" disabled={!!busy} onClick={() => void run("read", () => markRead(undefined, category))}><CheckCheck className="me-1.5 h-4 w-4" />{t("inbox.markAllRead")}</Button>
          </div>
        </div>
        {(error || inboxError) && <p role="alert" className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{error || inboxError}</p>}
        {!page && !error && !inboxError && <div role="status" className="flex justify-center p-12"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /><span className="sr-only">{t("inbox.loading")}</span></div>}
        {page?.items.length === 0 && <div className="flex flex-col items-center gap-3 rounded-2xl bg-muted/30 px-4 py-16 text-sm text-muted-foreground"><Inbox className="h-7 w-7" /><p>{t("inbox.empty")}</p></div>}
        <div className="space-y-2">{page?.items.map((notice) => <article key={notice.id} className={cn("flex min-w-0 gap-3 rounded-2xl border p-4 text-sm", notice.read_at ? "border-border/30 bg-muted/15" : "border-border/60 bg-muted/35")}>
          <div className="pt-0.5">{icon(notice)}</div>
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h2 className="text-sm font-medium">{t(`inbox.kind.${notice.kind}`, { defaultValue: t(`inbox.category.${notice.category}`) })}</h2>
              <span className="text-xs text-muted-foreground">{t(`inbox.status.${notice.status}`, { defaultValue: notice.status })}</span>
              {!notice.read_at && <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-label={t("inbox.unread")} />}
              <time className="ms-auto text-[11px] text-muted-foreground" dateTime={new Date(notice.created_at).toISOString()}>{new Intl.DateTimeFormat(i18n.resolvedLanguage, { dateStyle: "short", timeStyle: "short" }).format(notice.created_at)}</time>
            </div>
            {notice.data.session_title && <p className="break-words text-xs text-muted-foreground [overflow-wrap:anywhere]">{notice.data.session_title}</p>}
            {notice.body && <p className="whitespace-pre-wrap break-words text-sm leading-6 [overflow-wrap:anywhere]">{notice.body}</p>}
            <div className="flex flex-wrap items-center gap-2">
              {notice.session_key && <Button variant="ghost" size="sm" disabled={!!busy || notice.status === "unavailable"} className="-ms-2 text-muted-foreground" onClick={() => void run(notice.id, async () => {
                const target = await client.requestMutation<{ session_key: string | null }>("instance.action", { action: "inbox.open", values: { id: notice.id } });
                await markRead([notice.id]);
                if (!target.session_key) throw new Error(t("inbox.conversationUnavailable"));
                onSelect(target.session_key);
              })}><ExternalLink className="me-1.5 h-3.5 w-3.5" />{t(notice.kind === "question" && notice.status === "pending" ? "inbox.answer" : "inbox.openConversation")}</Button>}
              {notice.kind === "pairing" && notice.status === "pending" && (["approve", "deny"] as const).map((action) => <Button key={action} variant={action === "approve" ? "default" : "ghost"} size="sm" disabled={!!busy} onClick={() => void run(notice.id, async () => { await runPairingAction(client, action, notice.data.code!); await refresh(); })}>{t(`inbox.${action}`)}</Button>)}
              {!notice.read_at && <Button variant="ghost" size="sm" disabled={!!busy} className="text-xs text-muted-foreground" onClick={() => void run(notice.id, () => markRead([notice.id]))}>{t("inbox.markRead")}</Button>}
            </div>
          </div>
        </article>)}</div>
        {page?.next_before && <Button variant="ghost" className="w-full" disabled={!!busy} onClick={() => void run("more", async () => { const next = await load(category, page.next_before!); setPage({ ...next, items: [...page.items, ...next.items] }); })}>{t("inbox.loadMore")}</Button>}
      </div>
    </div>
  </section>;
}
