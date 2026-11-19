import type { InboxCategory, InboxNotice, InboxPage } from "./store";

export interface InboxReadReceipt {
  ok: true;
  read_at: number;
  unread: Record<InboxCategory, number>;
  revision?: number;
}

export function markInboxItemsRead(items: InboxNotice[], receipt: Pick<InboxReadReceipt, "read_at" | "revision">,
  ids?: string[], category?: InboxCategory): InboxNotice[] {
  return items.map(item => (!ids || ids.includes(item.id)) && (!category || item.category === category)
    && (receipt.revision === undefined || item.revision === undefined || item.revision <= receipt.revision)
    ? { ...item, read_at: item.read_at ?? receipt.read_at } : item);
}

export function applyInboxReadReceipt(page: InboxPage, receipt: InboxReadReceipt, ids?: string[], category?: InboxCategory): InboxPage {
  if (receipt.revision !== undefined && page.revision !== undefined && page.revision > receipt.revision) return page;
  return { ...page, ...(receipt.revision === undefined ? {} : { revision: receipt.revision }),
    unread: receipt.unread, items: markInboxItemsRead(page.items, receipt, ids, category) };
}
