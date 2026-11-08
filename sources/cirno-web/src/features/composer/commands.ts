import type { SkillSummary } from "@/lib/contracts/skills";
import { SLASH_RECENTS_LIMIT, SLASH_RECENTS_STORAGE_KEY } from "./contracts";
export interface SlashPaletteCommand {
  command: string;
  title: string;
  description: string;
  icon: string;
  kind?: "skill";
  argHint?: string;
  detail: string;
  badge?: string;
  recent: boolean;
}

export function skillMatchRank(
  skill: SkillSummary,
  query: string,
): number | null {
  if (!query) return 0;
  const name = skill.name.toLowerCase();
  if (name === query) return 0;
  if (name.startsWith(query)) return 1;
  if (name.includes(query)) return 2;
  if (skill.description.toLowerCase().includes(query)) return 3;
  return null;
}

export function slashCommandI18nKey(command: string): string {
  return command.replace(/^\//, "").replace(/-/g, "_");
}

export function readSlashRecents(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(SLASH_RECENTS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed
          .filter((item): item is string => typeof item === "string")
          .slice(0, SLASH_RECENTS_LIMIT)
      : [];
  } catch {
    return [];
  }
}

export function storeSlashRecents(commands: string[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      SLASH_RECENTS_STORAGE_KEY,
      JSON.stringify(commands.slice(0, SLASH_RECENTS_LIMIT)),
    );
  } catch {
    // localStorage may be unavailable in private contexts; command insertion still works.
  }
}
