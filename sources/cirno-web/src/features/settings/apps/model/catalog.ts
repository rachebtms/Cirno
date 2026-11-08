import type { CliAppInfo, CliAppsPayload } from "@/lib/contracts/apps";
import type { McpPresetInfo, McpPresetsPayload } from "@/lib/contracts/mcp";
import type { AppsKindFilter } from "./contracts";
export type AppsCatalogItem =
  | { id: string; kind: "cli"; app: CliAppInfo }
  | { id: string; kind: "mcp"; preset: McpPresetInfo };

export function appsTitle(item: AppsCatalogItem): string {
  return item.kind === "cli" ? item.app.display_name : item.preset.display_name;
}

export function appsReady(item: AppsCatalogItem): boolean {
  if (item.kind === "cli") return item.app.installed;
  if (item.preset.enabled !== undefined) return item.preset.enabled;
  return item.preset.installed &&
    item.preset.configured &&
    item.preset.runtime_status === "connected";
}

function appsSearchText(item: AppsCatalogItem): string {
  if (item.kind === "cli") {
    const app = item.app;
    return [
      app.display_name,
      app.name,
      app.category,
      app.description,
      app.requires,
      app.entry_point,
      app.source,
    ]
      .join(" ")
      .toLowerCase();
  }
  const preset = item.preset;
  return [
    preset.display_name,
    preset.name,
    preset.category,
    preset.description,
    preset.requires,
    preset.note,
    preset.transport,
    preset.source ?? "",
  ]
    .join(" ")
      .toLowerCase();
}

export function catalogEntries(cli: CliAppsPayload | null, mcp: McpPresetsPayload | null, filter: AppsKindFilter, query: string): AppsCatalogItem[] {
  const normalized = query.trim().toLowerCase();
  const items: AppsCatalogItem[] = [...(cli?.apps ?? []).map(app => ({ id: `cli:${app.name}`, kind: "cli" as const, app })), ...(mcp?.presets ?? []).map(preset => ({ id: `mcp:${preset.name}`, kind: "mcp" as const, preset }))];
  return items.filter(item => {
    const matches = filter === "ready" ? appsReady(item) : filter === "cli" ? item.kind === "cli" || item.preset.source === "agent-plugin" : item.kind === "mcp" && item.preset.source !== "agent-plugin";
    return matches && (!normalized || appsSearchText(item).includes(normalized));
  }).sort((left, right) => Number(!appsReady(left)) - Number(!appsReady(right)) || appsTitle(left).localeCompare(appsTitle(right)));
}
