import type { ChatSummary } from "@/lib/contracts/conversations";
import type { CliAppInfo } from "@/lib/contracts/apps";
import type { McpPresetInfo } from "@/lib/contracts/mcp";
import type { SessionMention, OutboundCliAppMention, OutboundMcpPresetMention } from "@/lib/contracts/messages";
export function sessionMentionOptions(
  sessions: ChatSummary[],
): SessionMention[] {
  return sessions.flatMap((session) => {
    if (!session.handle) return [];
    return [
      {
        id: session.handle.id,
        name: session.handle.name,
        session_key: session.key,
        title: session.title?.trim() || session.preview.trim(),
      },
    ];
  });
}

export function cliAppMentionPayload(app: CliAppInfo): OutboundCliAppMention {
  return {
    name: app.name,
    display_name: app.display_name,
    category: app.category,
    entry_point: app.entry_point,
    logo_url: app.logo_url ?? null,
    brand_color: app.brand_color ?? null,
  };
}

export function mcpPresetMentionPayload(
  preset: McpPresetInfo,
): OutboundMcpPresetMention {
  return {
    name: preset.name,
    display_name: preset.display_name,
    category: preset.category,
    transport: preset.transport,
    status: preset.status,
    configured: preset.configured,
    logo_url: preset.logo_url ?? null,
    brand_color: preset.brand_color ?? null,
  };
}
