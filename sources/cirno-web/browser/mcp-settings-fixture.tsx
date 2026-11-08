import { Button } from "@heroui/react";
import { useRef, useState } from "react";
import { Server } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { McpManagementDialog, type McpManagementTab } from "@/features/settings/mcp/McpManagementDialog";
import { SharedProxySetupDialog } from "@/features/settings/shared/SharedProxySetupDialog";
import type { McpPresetInfo } from "@/lib/contracts/mcp";

const initial: McpPresetInfo = {
  name: "research", display_name: "Research library", category: "research", description: "Search and maintain a shared research library.",
  docs_url: "https://example.com/docs", transport: "streamableHttp", auth: null, requires: "", note: "", install_supported: true,
  installed: true, configured: true, available: true, status: "configured", runtime_status: "connected", required_fields: [],
  connection_summary: "https://example.com/mcp", tool_names: ["search_papers", "write_note", `inspect_${"long_name_".repeat(12)}`], tool_count: 3,
  enabled_tools: ["*"], source: "custom",
};
export function McpSettingsFixture() {
  useTheme();
  const [open, setOpen] = useState(true);
  const [tab, setTab] = useState<McpManagementTab>("tools");
  const [proxy, setProxy] = useState(false);
  const [preset, setPreset] = useState(initial);
  const [values, setValues] = useState<Record<string, string>>({});
  const saves = useRef(0);
  return <main className="p-6"><Button onPress={() => setOpen(true)}>Manage research library</Button>
    {open && <McpManagementDialog preset={preset} tab={tab} onTabChange={setTab} icon={<Server size={22} />} statusLabel="Connected" statusTone="success"
      values={values} actionKey={null} onOpenChange={setOpen} onFieldChange={(_name, field, value) => setValues(current => ({ ...current, [field]: value }))}
      onAction={() => {}} onOAuthConnect={() => {}} onToolsChange={(_name, tools) => setPreset(current => ({ ...current, enabled_tools: tools }))}
      onConfigureProxy={() => setProxy(true)} configEditor={{ load: async () => JSON.stringify({ url: "https://example.com/mcp", toolTimeout: 120 }), save: async () => {
        if (++saves.current === 1) throw new Error("Configuration save failed");
      } }} />}
    {proxy && <SharedProxySetupDialog busy={false} onClose={() => setProxy(false)} onSave={async () => {}} />}
  </main>;
}
