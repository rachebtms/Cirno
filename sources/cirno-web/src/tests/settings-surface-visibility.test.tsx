import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { WorkbenchRoute } from "@/app/WorkbenchRoute";
import type { ShellSurfaceProps } from "@/app/surface-contract";
import type { WorkspaceRoute } from "@/features/workbench/contracts";

vi.mock("@/app/navigation", async () => {
  const { usePageVisibility } = await import("@/hooks/usePageVisibility");
  function Probe() { return <output data-testid="visibility">{String(usePageVisibility())}</output>; }
  return { SettingsView: Probe, InboxPage: Probe, isSettingsSectionKey: () => true };
});
vi.mock("@/app/WorkbenchConversation", () => ({ WorkbenchConversation: () => null }));

it.each(["settings", "inbox"] as const)("exposes visibility to the kept-mounted %s surface", (view) => {
  const route = { view, activeKey: null, settingsSection: "apps" } as WorkspaceRoute;
  const surface = {
    workspaceState: { sidebarState: { title_overrides: {} } },
    conversationActions: {}, conversationLifecycle: {}, workspaceActions: {}, runtimeActions: {}, inputs: {},
  } as unknown as ShellSurfaceProps;
  const props = { route, focused: true, surface };
  const { rerender } = render(<WorkbenchRoute {...props} visible />);
  const probe = screen.getByTestId("visibility");
  expect(probe).toHaveTextContent("true");
  rerender(<WorkbenchRoute {...props} focused={false} visible={false} />);
  expect(screen.getByTestId("visibility")).toBe(probe);
  expect(probe).toHaveTextContent("false");
  rerender(<WorkbenchRoute {...props} visible />);
  expect(screen.getByTestId("visibility")).toBe(probe);
  expect(probe).toHaveTextContent("true");
});
