import type {
  PanelKind,
  WorkspaceModule,
  WorkspacePanelContribution,
} from "./contracts";
import { createElement, type ReactNode } from "react";

/** Compose feature contributions once, before mounting the workspace. */
export function createWorkspaceRegistry(modules: readonly WorkspaceModule[]) {
  const owners = new Set<string>();
  const panels = new Map<PanelKind, WorkspacePanelContribution>();
  for (const module of modules) {
    if (owners.has(module.id))
      throw new Error(`Workspace module '${module.id}' is registered twice`);
    owners.add(module.id);
    for (const panel of module.panels) {
      if (panels.has(panel.kind))
        throw new Error(`Workspace panel '${panel.kind}' is registered twice`);
      panels.set(panel.kind, Object.freeze({ ...panel }));
    }
  }
  return Object.freeze({
    wrap: (children: ReactNode) =>
      modules.reduceRight(
        (content, module) =>
          module.Provider
            ? createElement(module.Provider, { children: content })
            : content,
        children,
      ),
    has: (kind: string): kind is PanelKind => panels.has(kind as PanelKind),
    get(kind: PanelKind): WorkspacePanelContribution {
      const panel = panels.get(kind);
      if (!panel)
        throw new Error(`Workspace panel '${kind}' is not registered`);
      return panel;
    },
    menu: Object.freeze(
      [...panels.values()].filter((panel) => panel.showInMenu),
    ),
  });
}

export type WorkspaceRegistry = ReturnType<typeof createWorkspaceRegistry>;
