import { useEffect, useRef, useState } from "react";
import type { McpManagementDialogProps } from "./contracts";
import { normalizeTools } from "./tools";

export function useMcpManagement(options: McpManagementDialogProps) {
  const { preset, values, actionKey, tab, onAction, onOpenChange, onOAuthConnect } = options;
  const inventory = useRef(preset.tool_names ?? []);
  const toolNames = preset.tool_names?.length ? preset.tool_names : inventory.current;
  useEffect(() => { if (preset.tool_names?.length) inventory.current = preset.tool_names; }, [preset.tool_names]);
  const [query, setQuery] = useState("");
  const [enabled, setEnabled] = useState(preset.enabled_tools ?? ["*"]);
  const inspected = useRef(false);
  const busy = ["test", "reconnect", "remove", "enable", "disable", "tools", "oauth", "proxy", "edit"].some(action => actionKey === `${action}:${preset.name}`);
  const toolsBusy = actionKey === `tools:${preset.name}`;
  const testBusy = actionKey === `test:${preset.name}`;
  const connected = preset.installed && preset.configured;
  const remote = preset.transport !== "stdio";
  const useProxy = values.use_proxy ?? String(preset.use_proxy ?? false);
  const proxyDirty = remote && useProxy !== String(preset.use_proxy ?? false);
  const connectionValues = remote ? { ...values, use_proxy: useProxy } : values;
  const selected = enabled.includes("*") ? toolNames : enabled;
  const selectedCount = enabled.includes("*") ? preset.tool_count ?? toolNames.length : enabled.length;
  const toolsDirty = normalizeTools(enabled).join("\n") !== normalizeTools(preset.enabled_tools ?? ["*"]).join("\n");
  const requiredComplete = preset.required_fields.filter(field => field.required && !field.configured).every(field => values[field.name]?.trim());
  useEffect(() => {
    if (tab !== "tools" || !connected || toolNames.length || busy || preset.error || inspected.current) return;
    inspected.current = true;
    onAction("test", preset.name);
  }, [tab, connected, toolNames.length, busy, preset.error, preset.name, onAction]);
  const changeTools = (tools: string[]) => setEnabled(tools.length === toolNames.length ? ["*"] : tools);
  const refreshTools = () => { inspected.current = true; onAction("test", preset.name); };
  const applyProxy = () => { onOpenChange(false); onAction("proxy", preset.name, { use_proxy: useProxy }); };
  const connect = () => {
    onOpenChange(false);
    if (preset.auth === "oauth") onOAuthConnect(preset.name, connected, connectionValues);
    else if (connected && proxyDirty) onAction("proxy", preset.name, { use_proxy: useProxy });
    else onAction(connected ? "reconnect" : "enable", preset.name, connected ? values : connectionValues);
  };
  return { query, setQuery, toolNames, filteredTools: toolNames.filter(name => name.toLowerCase().includes(query.trim().toLowerCase())),
    selected, selectedCount, enabled, changeTools, selectAll: () => setEnabled(["*"]), clear: () => setEnabled([]),
    busy, toolsBusy, testBusy, connected, connectionValues, proxyDirty, toolsDirty, requiredComplete, connect, applyProxy, refreshTools,
    applyTools: () => options.onToolsChange(preset.name, enabled),
    remove: () => { onOpenChange(false); onAction("remove", preset.name); } };
}
export type McpManagementModel = ReturnType<typeof useMcpManagement>;
