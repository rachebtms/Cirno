import catalog from "../../../cirno-core/agent/tools/names.json";

const implementationNames = new Map(Object.entries(catalog.names).map(([id, name]) => [name, id]));
const implementationGroups = new Map(Object.entries(catalog.action_groups).map(([id, group]) => [group, id]));

/** Shared names for new tool calls and the existing persisted activity history. */
export function implementationToolName(name: string): string {
  const dotted = name.toLowerCase().replaceAll("__", ".");
  return implementationNames.get(dotted) ?? implementationGroups.get(dotted.split(".")[0])
    ?? name.toLowerCase().split(".").pop() ?? name.toLowerCase();
}

export function toolAction(name: string): string | undefined {
  const parts = name.replaceAll("__", ".").split(".");
  return parts.length === 2 && implementationGroups.has(parts[0]) ? parts[1] : undefined;
}

export function displayToolName(name: string): string {
  return name.replaceAll("__", ".");
}

export function publicToolName(name: string, action?: string): string | undefined {
  const id = name as keyof typeof catalog.names;
  if (id in catalog.names) return catalog.names[id];
  const group = name as keyof typeof catalog.action_groups;
  return group in catalog.action_groups && action ? `${catalog.action_groups[group]}.${action}` : undefined;
}
