import { deriveTitle } from "@/lib/format";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { SidebarSortMode } from "@/lib/contracts/conversation-preferences";

export function displayTitle(
  session: Pick<ChatSummary, "key" | "title" | "preview">,
  titleOverrides: Record<string, string>,
  fallbackTitle: string,
): string {
  return (
    titleOverrides[session.key]?.trim()
    || session.title?.trim()
    || deriveTitle(session.preview, fallbackTitle)
  );
}


export function sortProjectSessions(
  sessions: ChatSummary[],
  sort: SidebarSortMode,
  titleOverrides: Record<string, string>,
  sessionOrder: string[],
  pinned: Set<string>,
  archived: Set<string>,
): ChatSummary[] {
  return sortSessions(sessions, sort, titleOverrides, sessionOrder).sort((a, b) => {
    const pinOrder = Number(pinned.has(b.key)) - Number(pinned.has(a.key));
    if (pinOrder !== 0) return pinOrder;
    const archiveOrder = Number(archived.has(a.key)) - Number(archived.has(b.key));
    if (archiveOrder !== 0) return archiveOrder;
    return 0;
  });
}

export function sortSessions(
  sessions: ChatSummary[],
  sort: SidebarSortMode,
  titleOverrides: Record<string, string>,
  sessionOrder: string[],
): ChatSummary[] {
  const copy = [...sessions];
  const order = new Map(sessionOrder.map((key, index) => [key, index]));
  copy.sort((a, b) => {
    if (sort === "manual") {
      const aIndex = order.get(a.key);
      const bIndex = order.get(b.key);
      if (aIndex !== undefined && bIndex !== undefined) return aIndex - bIndex;
      if (aIndex === undefined && bIndex !== undefined) return -1;
      if (aIndex !== undefined && bIndex === undefined) return 1;
      return sessionTime(b, "updatedAt") - sessionTime(a, "updatedAt");
    }
    if (sort === "title_asc") {
      const titleOrder = titleForSort(a, titleOverrides).localeCompare(
        titleForSort(b, titleOverrides),
        "en",
        { numeric: true, sensitivity: "base" },
      );
      if (titleOrder !== 0) return titleOrder;
      return sessionTime(b, "updatedAt") - sessionTime(a, "updatedAt");
    }
    const aTime = sessionTime(a, sort === "created_desc" ? "createdAt" : "updatedAt");
    const bTime = sessionTime(b, sort === "created_desc" ? "createdAt" : "updatedAt");
    return bTime - aTime;
  });
  return copy;
}

function titleForSort(
  session: ChatSummary,
  titleOverrides: Record<string, string>,
): string {
  return (
    titleOverrides[session.key]?.trim()
    || session.title?.trim()
    || deriveTitle(session.preview, "new chat")
  ).toLocaleLowerCase("en");
}

function sessionTime(session: ChatSummary, field: "createdAt" | "updatedAt"): number {
  const ts = Date.parse(session[field] ?? "");
  return Number.isFinite(ts) ? ts : 0;
}
