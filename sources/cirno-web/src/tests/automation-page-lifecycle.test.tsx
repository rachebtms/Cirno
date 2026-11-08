import userEvent from "@testing-library/user-event";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { jsonResponse, settingsPayload, renderSettingsView, installSettingsViewTestHooks } from "@/tests/settings-test-utils";

async function selectAutomationFilter(name: string) {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /^Filter/ }));
  await user.click(await screen.findByRole("menuitemradio", { name }));
}

describe("Automation page lifecycle", () => {
  installSettingsViewTestHooks();

  it("creates an automation from the standalone empty state", async () => {
    const onStartAutomationChat = vi.fn().mockResolvedValue(true);
    const settings = settingsPayload();
    settings.providers = [{
      id: "openai",
      name: "OpenAI",
      configured: true,
    }];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(settings);
      if (url === "/v0/webui/automations") return jsonResponse({ jobs: [] });
      return jsonResponse({});
    }));

    renderSettingsView({
      initialSection: "automations",
      initialSettings: settings,
      showSidebar: false,
      onStartAutomationChat,
    });

    expect(screen.getByRole("heading", { name: "Automations" })).toBeInTheDocument();
    await waitFor(() => expect(document.querySelectorAll(".automation-calendar-day").length).toBeGreaterThanOrEqual(35));
    const input = screen.getByRole("textbox", { name: "Describe an automation" });
    expect(input).toHaveAttribute(
      "placeholder",
      "What would you like to automate?",
    );
    fireEvent.change(input, { target: { value: "Summarize updates every weekday at 9" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(onStartAutomationChat).toHaveBeenCalledWith(
      "Summarize updates every weekday at 9",
      undefined,
      { intent: "create_automation" },
      "primary",
    ));
  });

  it("offers a way out of an empty automations filter", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(settingsPayload());
      if (url === "/v0/webui/automations") {
        return jsonResponse({
          jobs: [{
            id: "job-1",
            name: "Daily summary",
            enabled: true,
            schedule: { kind: "cron", expr: "0 9 * * *" },
            payload: { message: "Summarize the day" },
            state: { next_run_at_ms: Date.now() + 60_000 },
          }],
        });
      }
      return jsonResponse({});
    }));

    renderSettingsView({
      initialSection: "automations",
      initialSettings: settingsPayload(),
      showSidebar: false,
    });

    expect(await screen.findByRole("button", { name: /Daily summary/ })).toBeInTheDocument();
    await selectAutomationFilter("Disabled 0");
    expect(screen.queryByRole("button", { name: /Daily summary/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Today" })).toBeVisible();
    await selectAutomationFilter("All 1");
    expect(await screen.findByRole("button", { name: /Daily summary/ })).toBeInTheDocument();
  });

  it("reveals status filters on demand and keeps every option selectable", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/v0/settings") return jsonResponse(settingsPayload());
      if (String(input) === "/v0/webui/automations") {
        return jsonResponse({ jobs: [
          {
            id: "heartbeat", name: "heartbeat", enabled: true, protected: true,
            schedule: { kind: "every", every_ms: 1_800_000 },
            payload: { message: "System-managed automation" }, state: { next_run_at_ms: Date.now() + 60_000 },
          },
          {
            id: "paused-job", name: "Paused reminder", enabled: false,
            schedule: { kind: "every", every_ms: 86_400_000 },
            payload: { message: "Check the repo" },
            state: { last_run_at_ms: Date.now() - 60_000, last_status: "ok" },
          },
        ] });
      }
      return jsonResponse({});
    }));
    renderSettingsView({ initialSection: "automations", initialSettings: settingsPayload(), showSidebar: false });

    const trigger = await screen.findByRole("button", { name: "Filter" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
    const menu = screen.getByRole("menu", { name: "Filter" });
    expect(within(menu).getAllByRole("menuitemradio")).toHaveLength(4);
    expect(within(menu).getByRole("menuitemradio", { name: "All 1" })).toHaveAttribute("aria-checked", "true");
    expect(within(menu).queryByRole("menuitemradio", { name: /System/ })).not.toBeInTheDocument();
    fireEvent.click(within(menu).getByRole("menuitemradio", { name: "Disabled 1" }));
    expect(screen.getByRole("button", { name: "Filter: Disabled" })).toBeVisible();
    expect(screen.getByRole("button", { name: /Paused reminder/ })).toBeVisible();
    expect(screen.queryByRole("button", { name: /heartbeat/ })).not.toBeInTheDocument();

  });

  it("coalesces focus refreshes while automations are already loading", async () => {
    let resolveAutomations!: (response: Response) => void;
    const pendingAutomations = new Promise<Response>((resolve) => {
      resolveAutomations = resolve;
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/v0/settings") return jsonResponse(settingsPayload());
      if (url === "/v0/webui/automations") return pendingAutomations;
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    renderSettingsView({
      initialSection: "automations",
      initialSettings: settingsPayload(),
      showSidebar: false,
    });

    await waitFor(() => {
      expect(fetchMock.mock.calls.filter(([input]) => (
        String(input) === "/v0/webui/automations"
      ))).toHaveLength(1);
    });
    window.dispatchEvent(new Event("focus"));
    window.dispatchEvent(new Event("focus"));

    expect(fetchMock.mock.calls.filter(([input]) => (
      String(input) === "/v0/webui/automations"
    ))).toHaveLength(1);
    await act(async () => {
      resolveAutomations(jsonResponse({ jobs: [] }));
      await pendingAutomations;
    });
  });
});
