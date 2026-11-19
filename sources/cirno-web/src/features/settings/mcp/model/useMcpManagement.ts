import { useEffect, useRef, useState } from "react";
import type { McpManagementDialogProps } from "./contracts";
import { normalizeTools } from "./tools";
import { useLifetime } from "@/ui/resources/useLifetime";

export function useMcpManagement(options: McpManagementDialogProps) {
  const { preset, values, actionKey, tab, onAction, onOpenChange, onOAuthConnect } = options;
  const isCurrent = useLifetime(preset.name);
  const busyNow = useRef(false);
  const inventory = useRef(preset.tool_names ?? []);
  const freshEmpty = actionKey !== `test:${preset.name}` && !preset.error
    && Boolean(preset.checked_at) && preset.tool_count === 0 && preset.tool_names?.length === 0;
  const toolNames = preset.inventory_stale ? []
    : preset.tool_names?.length || freshEmpty ? preset.tool_names ?? [] : inventory.current;
  useEffect(() => {
    if (preset.inventory_stale) inventory.current = [];
    else if (preset.tool_names?.length || freshEmpty) inventory.current = preset.tool_names ?? [];
  }, [preset.tool_names, freshEmpty, preset.inventory_stale]);
  const [query, setQueryValue] = useState("");
  const savedScope = normalizeTools(preset.enabled_tools ?? ["*"]).join("\n");
  const [scope, setScope] = useState({ basis: savedScope, enabled: preset.enabled_tools ?? ["*"] });
  if (scope.basis !== savedScope) {
    setScope({ basis: savedScope, enabled: normalizeTools(scope.enabled).join("\n") === scope.basis
      ? preset.enabled_tools ?? ["*"] : scope.enabled });
  }
  const enabled = scope.enabled;
  const scopeNow = useRef(scope);
  scopeNow.current = scope;
  const setEnabled = (enabled: string[]) => {
    if (isCurrent() && !busyNow.current) setScope({ basis: savedScope, enabled });
  };
  const inspected = useRef(false);
  const busy = ["test", "reconnect", "remove", "enable", "disable", "tools", "oauth", "proxy", "edit"].some(action => actionKey === `${action}:${preset.name}`);
  busyNow.current = busy;
  const toolsBusy = actionKey === `tools:${preset.name}`;
  const testBusy = actionKey === `test:${preset.name}`;
  const connected = preset.installed && preset.configured;
  const remote = preset.transport !== "stdio";
  const useProxy = values.use_proxy ?? String(preset.use_proxy ?? false);
  const proxyDirty = remote && useProxy !== String(preset.use_proxy ?? false);
  const fieldsDirty = preset.required_fields.some(field => values[field.name]?.trim());
  const connectionValues = remote ? { ...values, use_proxy: useProxy } : values;
  const connectionNow = useRef({ preset, values });
  connectionNow.current = { preset, values };
  const selected = enabled.includes("*") ? toolNames : enabled;
  const selectedCount = enabled.includes("*") ? toolNames.length : toolNames.filter(name => enabled.includes(name)).length;
  const toolsDirty = normalizeTools(enabled).join("\n") !== normalizeTools(preset.enabled_tools ?? ["*"]).join("\n");
  const requiredComplete = preset.required_fields.filter(field => field.required && !field.configured).every(field => values[field.name]?.trim());
  useEffect(() => {
    if (tab !== "tools" || !connected || toolNames.length || busy || preset.error || inspected.current) return;
    inspected.current = true;
    onAction("test", preset.name);
  }, [tab, connected, toolNames.length, busy, preset.error, preset.name, onAction]);
  // Selecting the known tool list does not grant resources, prompts or future
  // tools. Only the explicit all-tools action requests wildcard capabilities.
  const changeTools = (tools: string[]) => setEnabled(tools);
  const canAct = () => isCurrent() && !busyNow.current;
  const canSubmitConnection = () => canAct()
    && connectionNow.current.preset === preset && connectionNow.current.values === values;
  const refreshTools = () => { if (!canAct()) return; inspected.current = true; onAction("test", preset.name); };
  const applyProxy = () => { if (!canSubmitConnection()) return; onOpenChange(false); onAction("proxy", preset.name, { use_proxy: useProxy }); };
  const connect = () => {
    if (!canSubmitConnection()) return;
    onOpenChange(false);
    if (preset.auth === "oauth") onOAuthConnect(preset.name, connected, connectionValues);
    else if (fieldsDirty) onAction("enable", preset.name, connectionValues);
    else if (connected && proxyDirty) onAction("proxy", preset.name, { use_proxy: useProxy });
    else onAction(connected ? "reconnect" : "enable", preset.name, connected ? values : connectionValues);
  };
  return { query, setQuery: (query: string) => { if (isCurrent()) setQueryValue(query); }, toolNames, filteredTools: toolNames.filter(name => name.toLowerCase().includes(query.trim().toLowerCase())),
    selected, selectedCount, enabled, changeTools, selectAll: () => setEnabled(["*"]), clear: () => setEnabled([]),
    busy, toolsBusy, testBusy, connected, connectionValues, proxyDirty, fieldsDirty, toolsDirty, requiredComplete, connect, applyProxy, refreshTools,
    applyTools: () => { if (canAct() && scopeNow.current === scope) options.onToolsChange(preset.name, enabled); },
    remove: () => { if (!canAct()) return; onOpenChange(false); onAction("remove", preset.name); } };
}
export type McpManagementModel = ReturnType<typeof useMcpManagement>;
