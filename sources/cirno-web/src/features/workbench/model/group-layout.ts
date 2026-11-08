import type { TabGroup } from "../contracts";
import { isRecord } from "@/lib/record";
const KEY = "cirno-webui.tab-groups.v1";
export interface GroupLayout { enabled: boolean; focused: TabGroup; selected: [string | null, string | null]; ratio: number }
export function readGroupLayout(): { layout: GroupLayout; error: string } {
  const fallback: GroupLayout = { enabled: false, focused: 0, selected: [null, null], ratio: 50 };
  try {
    const value: unknown = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (value === null) return { layout: fallback, error: "" };
    if (!isRecord(value) || typeof value.enabled !== "boolean" || (value.focused !== 0 && value.focused !== 1) ||
      !Array.isArray(value.selected) || value.selected.length !== 2 || value.selected.some(id => id !== null && typeof id !== "string") ||
      typeof value.ratio !== "number" || value.ratio < 25 || value.ratio > 75) throw new Error("Saved tab groups have an invalid format");
    return { layout: value as unknown as GroupLayout, error: "" };
  } catch (reason) { return { layout: fallback, error: `Could not restore tab groups: ${String(reason)}` }; }
}
export function saveGroupLayout(layout: GroupLayout) { localStorage.setItem(KEY, JSON.stringify(layout)); }
