import { installAppTestLifecycle } from "./helpers/app-harness";
import { render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "@/App";
import { readShellRoute } from "@/app/navigation";
import { writeShellRoute } from "@/app/route-history";

describe("workspace route restoration", () => {
  installAppTestLifecycle();
  it.each(["settings", "automations", "inbox"] as const)(
    "restores the selected %s tab without duplicating it",
    async (view) => {
      const route = {
        view,
        activeKey: null,
        settingsSection: view === "automations" ? ("automations" as const) : ("overview" as const),
        tabId: `${view}:selected`,
      };
      const sibling = { ...route, tabId: `${view}:other` };
      localStorage.setItem(
        "cirno-webui.workspace-tabs.v1",
        JSON.stringify([route, sibling].map((route) => ({ id: route.tabId, type: "route", route }))),
      );
      writeShellRoute(route, true);
      render(<App />);
      const tabs = await screen.findByRole("tablist", { name: "Workspace tabs" });
      await waitFor(() => expect(within(tabs).getAllByRole("tab")).toHaveLength(1));
      expect(within(tabs).getByRole("tab", { selected: true }).id).toContain(`-tab-${view}`);
    },
  );
  it("does not attach a previous history entry's tab identity to a different URL", () => {
    writeShellRoute(
      { view: "automations", activeKey: null, settingsSection: "automations", tabId: "automations:old" },
      true,
    );
    window.history.replaceState(window.history.state, "", "/#/settings");
    expect(readShellRoute()).toMatchObject({ view: "settings" });
    expect(readShellRoute().tabId).toBeUndefined();
  });
});
