import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useClient } from "@/providers/ClientProvider";
import { showBrowserNotification } from "@/lib/browser-notifications";
import { playTurnCompleteSound } from "@/lib/notification-sound";

export const INBOX_CATEGORIES = ["operations", "conversations", "system"] as const;
export type InboxCategory = typeof INBOX_CATEGORIES[number];
export interface InboxNotice {
  seq: number; id: string; category: InboxCategory; kind: string; status: string;
  session_key: string | null; body: string; data: { approval_id?: string; operation?: string; arguments?: Record<string, unknown>; code?: string; media?: string[]; session_title?: string };
  created_at: number; read_at: number | null;
}
export interface InboxPage {
  items: InboxNotice[]; unread: Record<InboxCategory, number>; latest_seq: number; next_before: number | null;
}
const EMPTY: InboxPage = { items: [], unread: { operations: 0, conversations: 0, system: 0 }, latest_seq: 0, next_before: null };
interface InboxState {
  snapshot: InboxPage; error: string | null; connected: boolean;
  refresh: () => Promise<void>;
  load: (category?: InboxCategory, before?: number) => Promise<InboxPage>;
  markRead: (ids?: string[], category?: InboxCategory) => Promise<void>;
}
const Context = createContext<InboxState | null>(null);

export function InboxProvider({ children }: { children: ReactNode }) {
  const { client } = useClient();
  const { t } = useTranslation();
  const [snapshot, setSnapshot] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(client.status === "open");
  useEffect(() => {
    setConnected(client.status === "open");
    return client.onStatus((status) => setConnected(status === "open"));
  }, [client]);
  const cursor = useRef<number | null>(null);
  const pending = useRef<number | null>(null);
  const revision = useRef(0);
  const currentClient = useRef(client);
  currentClient.current = client;
  useEffect(() => { cursor.current = null; setSnapshot(EMPTY); setError(null); }, [client]);
  const load = useCallback((category?: InboxCategory, before?: number) => client.requestMutation<InboxPage>("instance.action", {
    action: "inbox.list", values: { ...(category ? { category } : {}), ...(before ? { before } : {}) },
  }), [client]);
  const refresh = useCallback(async () => {
    if (!connected || pending.current !== null) return;
    const stamp = ++revision.current;
    pending.current = stamp;
    try {
      const page = await load();
      if (stamp !== revision.current) return;
      if (!Array.isArray(page.items) || !page.unread) throw new Error(t("inbox.invalidResponse"));
      setSnapshot(page);
      setError(null);
      if (cursor.current !== null) {
        for (const notice of [...page.items].reverse()) {
          // Turn completion already has an immediate, privacy-safe notification path.
          if (notice.seq <= cursor.current || notice.read_at || notice.kind === "turn") continue;
          void showBrowserNotification(t(`inbox.browser.${notice.category}`), {
            key: "inbox:" + notice.id, category: notice.category,
            url: `${window.location.origin}/#/inbox?category=${notice.category}`,
          });
          if (notice.category !== "conversations") playTurnCompleteSound(notice.category);
        }
      }
      cursor.current = page.latest_seq;
    } catch (reason) {
      if (stamp === revision.current) setError(reason instanceof Error ? reason.message : String(reason));
    } finally { if (pending.current === stamp) pending.current = null; }
  }, [connected, load, t]);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 10000);
    const focused = () => void refresh();
    window.addEventListener("focus", focused);
    return () => { revision.current++; pending.current = null; window.clearInterval(timer); window.removeEventListener("focus", focused); };
  }, [refresh]);
  const markRead = useCallback(async (ids?: string[], category?: InboxCategory) => {
    await client.requestMutation("instance.action", { action: "inbox.read", values: { ids, category } });
    if (currentClient.current !== client) return;
    // A poll started before this write cannot restore unread rows or counts.
    revision.current++; pending.current = null;
    setSnapshot((current) => ({ ...current, items: current.items.map((item) =>
      (!ids || ids.includes(item.id)) && (!category || item.category === category) ? { ...item, read_at: Date.now() } : item) }));
    await refresh();
  }, [client, refresh]);
  return <Context.Provider value={{ snapshot, error, connected, refresh, load, markRead }}>{children}</Context.Provider>;
}

export function useInbox() {
  const context = useContext(Context);
  if (!context) throw new Error("InboxProvider is required");
  return context;
}
