import type { CliAppInfo } from "@/lib/contracts/apps";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type {
  UICliAppAttachment,
  UIMcpPresetAttachment,
} from "@/lib/contracts/messages";

export function mergeMcpMentionPresets(
  presets: McpPresetInfo[],
  attachments: UIMcpPresetAttachment[] | undefined,
): McpPresetInfo[] {
  if (!attachments?.length) return presets;
  const byName = new Map(
    presets.map((preset) => [preset.name.toLowerCase(), preset]),
  );
  for (const attachment of attachments) {
    const name = attachment.name?.trim();
    if (!name) continue;
    const existing = byName.get(name.toLowerCase());
    byName.set(name.toLowerCase(), {
      name,
      display_name: attachment.display_name || existing?.display_name || name,
      category: attachment.category || existing?.category || "mcp",
      description: existing?.description || "",
      docs_url: existing?.docs_url || "",
      transport: attachment.transport || existing?.transport || "mcp",
      requires: existing?.requires || "",
      note: existing?.note || "",
      install_supported: existing?.install_supported ?? true,
      installed: true,
      configured: attachment.configured ?? existing?.configured ?? true,
      available: existing?.available ?? true,
      status: attachment.status || existing?.status || "configured",
      logo_url: attachment.logo_url ?? existing?.logo_url ?? null,
      brand_color: attachment.brand_color ?? existing?.brand_color ?? null,
      required_fields: existing?.required_fields || [],
      connection_summary: existing?.connection_summary || "",
    });
  }
  return Array.from(byName.values());
}

export function mergeCliMentionApps(
  cliApps: CliAppInfo[],
  attachments: UICliAppAttachment[] | undefined,
): CliAppInfo[] {
  if (!attachments?.length) return cliApps;
  const byName = new Map(cliApps.map((app) => [app.name.toLowerCase(), app]));
  for (const attachment of attachments) {
    const name = attachment.name?.trim();
    if (!name) continue;
    const existing = byName.get(name.toLowerCase());
    byName.set(name.toLowerCase(), {
      name,
      display_name: attachment.display_name || existing?.display_name || name,
      category: attachment.category || existing?.category || "cli",
      description: existing?.description || "",
      requires: existing?.requires || "",
      source: existing?.source || "attached",
      entry_point: attachment.entry_point || existing?.entry_point || "",
      install_supported: existing?.install_supported ?? true,
      installed: true,
      available: existing?.available ?? true,
      status: existing?.status || "installed",
      logo_url: attachment.logo_url ?? existing?.logo_url ?? null,
      brand_color: attachment.brand_color ?? existing?.brand_color ?? null,
      skill_installed: existing?.skill_installed ?? true,
    });
  }
  return Array.from(byName.values());
}
