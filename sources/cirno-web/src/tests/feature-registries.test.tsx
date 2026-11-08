import { SETTINGS_SECTION_KEYS } from "@/app/navigation";
import { Workbench } from "@/features/workbench/Workbench";
import { settingsSections } from "@/features/settings/modules";
import { createSettingsRegistry } from "@/features/settings/registry";
import type { WorkspaceModule, WorkspacePanelProps } from "@/features/workbench/contracts";
import { createWorkspaceRegistry } from "@/features/workbench/registry";
import type { CirnoClient } from "@/lib/cirno-client";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Boxes } from "lucide-react";
import { useEffect } from "react";
import { describe, expect, it, vi } from "vitest";

function extensionModule(close: () => Promise<void>): WorkspaceModule {
  function Extension({ tab, active, registerClose }: WorkspacePanelProps) {
    useEffect(() => { registerClose(tab.id, close); }, [registerClose, tab.id]);
    return <p>{active ? "Extension is active" : "Extension is hidden"}</p>;
  }
  return {
    id: "research", panels: [{
      kind: "research.notes", titleKey: "Research notes", Icon: Boxes,
      Content: Extension, tabPolicy: "multiple", showInMenu: true
    }]
  };
}

describe("feature contributions", () => {
  it("opens independently registered panels in the real workspace and disposes them on close", async () => {
    const user = userEvent.setup();
    localStorage.clear();
    const close = vi.fn(async () => undefined);
    const panels = createWorkspaceRegistry([extensionModule(close)]);
    render(<Workbench client={{} as CirnoClient} route={{ view: "chat", activeKey: null, settingsSection: "overview" }}
      panels={panels} navigationSequence={0} title="New conversation" sessions={[]} onRouteVisibleChange={() => undefined}
      onRoute={() => undefined} onNewChat={() => undefined} beforeActivate={(action) => action()}>
      <p>Conversation</p>
    </Workbench>);
    await user.click(screen.getByRole("button", { name: "Open Research notes" }));
    expect(await screen.findByText("Extension is active")).toBeVisible();
    const tab = screen.getByRole("tab", { name: "Research notes" });
    expect(tab).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("button", { name: "Close Research notes" }));
    await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByText("Extension is active")).not.toBeInTheDocument());
  });

  it("rejects duplicate owners and panel identities before mounting", () => {
    const module = extensionModule(async () => undefined);
    expect(() => createWorkspaceRegistry([module, module])).toThrow("registered twice");
    expect(() => createWorkspaceRegistry([module, { ...module, id: "other" }])).toThrow("registered twice");
  });

  it("uses the same settings identities for navigation, routing and panel composition", () => {
    expect(settingsSections.navigation.every(section => SETTINGS_SECTION_KEYS.includes(section.key))).toBe(true);
    expect(settingsSections.get("account")?.Panel).toBeDefined();
    expect(settingsSections.get("backup")?.Panel).toBeDefined();
    const section = { key: "research.catalog" as const, icon: Boxes, fallback: "Research catalog", group: "research" };
    const registry = createSettingsRegistry([section]);
    expect(registry.has("research.catalog")).toBe(true);
    expect(registry.get("research.catalog")?.fallback).toBe("Research catalog");
    expect(() => createSettingsRegistry([section, section])).toThrow("registered twice");
  });
});
