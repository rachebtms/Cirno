import { deriveTitle } from "@/lib/format";
import type { ChatSummary, ProjectSummary, SidebarSortMode } from "@/lib/types";

export const COLLAPSED_CHATS_VISIBLE_COUNT = 8;

export interface SessionGroup {
  id: string;
  label: string;
  sessions: ChatSummary[];
  kind?: "project";
  projectPath?: string;
  projectKey?: string;
  updatedAt?: string | null;
}

export interface ChatGroupLabels {
  pinned: string;
  all: string;
  today: string;
  yesterday: string;
  earlier: string;
  archived: string;
  projects: string;
  fallbackTitle: string;
}

export interface ChatGroupingOptions {
  projects?: ProjectSummary[];
  pinnedKeys: string[];
  archivedKeys: string[];
  titleOverrides: Record<string, string>;
  projectNameOverrides: Record<string, string>;
  sessionOrder: string[];
  showArchived: boolean;
  sort: SidebarSortMode;
  defaultWorkspacePath?: string | null;
}

export function groupSessions(
  sessions: ChatSummary[],
  labels: ChatGroupLabels,
  options: ChatGroupingOptions,
): SessionGroup[] {
  if (options.projects !== undefined) {
    const visible = sessions.filter(session => !session.isGlobal && (options.showArchived || !options.archivedKeys.includes(session.key)));
    const grouped: SessionGroup[] = options.projects.map(project => ({
      id: `project:${project.id}`, label: project.name, kind: "project", projectKey: project.id,
      projectPath: project.working_directory,
      sessions: sortProjectSessions(visible.filter(session => session.projectId === project.id), options.sort, options.titleOverrides, options.sessionOrder, new Set(options.pinnedKeys), new Set(options.archivedKeys)),
    }));
    const ids = new Set(options.projects.map(project => project.id));
    const ordinary = visible.filter(session => !session.projectId || !ids.has(session.projectId));
    if (ordinary.length) grouped.push({id: "workspace:chats", label: labels.all,
      sessions: sortProjectSessions(ordinary, options.sort, options.titleOverrides, options.sessionOrder, new Set(options.pinnedKeys), new Set(options.archivedKeys))});
    return grouped;
  }

  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000;
  const buckets = new Map<string, ChatSummary[]>();
  const pinned = new Set(options.pinnedKeys);
  const archived = new Set(options.archivedKeys);

  const pinnedSessions: ChatSummary[] = [];
  const archivedSessions: ChatSummary[] = [];
  const normalSessions: ChatSummary[] = [];

  for (const session of sessions) {
    if (archived.has(session.key)) {
      if (options.showArchived) archivedSessions.push(session);
      continue;
    }
    if (pinned.has(session.key)) {
      pinnedSessions.push(session);
      continue;
    }
    if (options.sort === "title_asc" || options.sort === "manual") {
      normalSessions.push(session);
      continue;
    }
    const timestamp = Date.parse(session.updatedAt ?? session.createdAt ?? "");
    const label = Number.isFinite(timestamp) && timestamp >= startOfToday
      ? labels.today
      : Number.isFinite(timestamp) && timestamp >= startOfYesterday
        ? labels.yesterday
        : labels.earlier;
    const bucket = buckets.get(label) ?? [];
    bucket.push(session);
    buckets.set(label, bucket);
  }

  const groups: SessionGroup[] = [labels.today, labels.yesterday, labels.earlier]
    .map((label) => ({
      id: `date:${label}`,
      label,
      sessions: sortSessions(
        buckets.get(label) ?? [],
        options.sort,
        options.titleOverrides,
        options.sessionOrder,
      ),
    }))
    .filter((group) => group.sessions.length > 0);

  if ((options.sort === "title_asc" || options.sort === "manual") && normalSessions.length) {
    groups.push({
      id: "date:all",
      label: labels.all,
      sessions: sortSessions(
        normalSessions,
        options.sort,
        options.titleOverrides,
        options.sessionOrder,
      ),
    });
  }
  if (pinnedSessions.length) {
    groups.unshift({
      id: "pinned",
      label: labels.pinned,
      sessions: sortSessions(
        pinnedSessions,
        options.sort,
        options.titleOverrides,
        options.sessionOrder,
      ),
    });
  }
  if (archivedSessions.length) {
    groups.push({
      id: "archived",
      label: labels.archived,
      sessions: sortSessions(
        archivedSessions,
        options.sort,
        options.titleOverrides,
        options.sessionOrder,
      ),
    });
  }
  return groups;
}

export function limitGroups(
  groups: SessionGroup[],
  limit: number,
  activeKey: string | null,
  collapsedGroups: Record<string, boolean>,
): SessionGroup[] {
  let remaining = Math.max(0, limit);
  let activeVisible = !activeKey;
  const out: SessionGroup[] = [];

  for (const group of groups) {
    if (group.kind === "project" && group.sessions.length === 0) { out.push(group); continue; }
    if (isCollapsedProject(group, collapsedGroups)) {
      out.push({ ...group, sessions: [] });
      continue;
    }
    const visible = remaining > 0
      ? group.sessions.slice(0, remaining)
      : [];
    remaining -= visible.length;
    if (activeKey && visible.some((session) => session.key === activeKey)) {
      activeVisible = true;
    }
    if (visible.length > 0) {
      out.push({ ...group, sessions: visible });
    }
  }

  if (activeVisible || !activeKey) return out;

  for (const group of groups) {
    if (isCollapsedProject(group, collapsedGroups)) continue;
    const active = group.sessions.find((session) => session.key === activeKey);
    if (!active) continue;
    const existing = out.find((item) => item.id === group.id);
    if (existing) {
      existing.sessions = [...existing.sessions, active];
    } else {
      out.push({ ...group, sessions: [active] });
    }
    return out;
  }

  return out;
}

export function isCollapsedProject(
  group: SessionGroup,
  collapsedGroups: Record<string, boolean>,
): boolean {
  return group.kind === "project" && Boolean(collapsedGroups[group.id]);
}

export function isFoldableChatsGroup(group: SessionGroup): boolean {
  return group.id === "workspace:chats" || group.id === "date:all";
}

export function isFoldedChatsGroup(
  group: SessionGroup,
  collapsedGroups: Record<string, boolean>,
): boolean {
  return (
    isFoldableChatsGroup(group)
    && group.sessions.length > COLLAPSED_CHATS_VISIBLE_COUNT
    && collapsedGroups[group.id] !== false
  );
}

export function visibleSessionsForGroup(
  group: SessionGroup,
  activeKey: string | null,
  collapsedGroups: Record<string, boolean>,
): ChatSummary[] {
  if (!isFoldedChatsGroup(group, collapsedGroups)) {
    return group.sessions;
  }
  const visible = group.sessions.slice(0, COLLAPSED_CHATS_VISIBLE_COUNT);
  if (!activeKey || visible.some((session) => session.key === activeKey)) {
    return visible;
  }
  const active = group.sessions.find((session) => session.key === activeKey);
  return active ? [...visible, active] : visible;
}

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


function sortProjectSessions(
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
