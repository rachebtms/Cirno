import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AutomationsPage } from "@/features/automations/AutomationsPage";
import { AutomationEditDialog } from "@/features/automations/edit/AutomationEditDialog";
import type { AutomationsPageProps } from "@/features/automations/model/contracts";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { SettingsPayload } from "@/lib/contracts/settings";

const job: SessionAutomationJob = {
  id: "daily",
  name: "Daily research",
  enabled: true,
  schedule: { kind: "every", every_ms: 62_500 },
  payload: { message: "Review the latest experiment." },
  state: { next_run_at_ms: Date.now() + 3600_000 },
  origin: { channel: "websocket", session_key: "websocket:research" },
};
const defaults: AutomationsPageProps = {
  payload: { jobs: [job] },
  loading: false,
  filter: "all",
  actionKey: null,
  error: null,
  onFilterChange: vi.fn(),
  onAction: vi.fn(),
  onRequestEdit: vi.fn(),
  onRequestDelete: vi.fn(),
};
const models = {
  agent: {
    model: "openai/gpt-5-mini",
    provider: "openai",
    resolved_provider: "openai",
    model_preset: "fast",
  },
  model_presets: [
    {
      id: "fast",
      name: "Fast",
      model: "openai/gpt-5-mini",
      provider: "openai",
      active: true,
      is_default: false,
    },
    {
      id: "deep",
      name: "Deep",
      model: "openai/gpt-5",
      provider: "openai",
      active: false,
      is_default: false,
    },
  ],
  model_call_order: ["fast", "deep"],
  providers: [{ id: "openai", name: "OpenAI", configured: true }],
} as SettingsPayload;
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Automation page ownership", () => {
  it("keeps the chosen view and existing tasks during a metadata refresh", async () => {
    const user = userEvent.setup();
    const view = render(
      <AutomationsPage {...defaults} payload={null} loading />,
    );
    await user.click(screen.getByRole("tab", { name: "Tasks" }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading automations...",
    );
    view.rerender(<AutomationsPage {...defaults} />);
    expect(
      screen.getByRole("button", { name: /^Daily research/ }),
    ).toBeEnabled();
    view.rerender(<AutomationsPage {...defaults} loading />);
    expect(
      screen.getByRole("button", { name: /^Daily research/ }),
    ).toBeEnabled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Tasks" }),
    ).toHaveAttribute("aria-selected", "true");
  });
  it("keeps an inspected task through filtering and closes when it is removed", async () => {
    const user = userEvent.setup();
    const view = render(<AutomationsPage {...defaults} />);
    await user.click(screen.getByRole("tab", { name: "Tasks" }));
    await user.click(screen.getByRole("button", { name: /^Daily research/ }));
    view.rerender(
      <AutomationsPage
        {...defaults}
        filter="active"
        payload={{ jobs: [{ ...job, enabled: false }] }}
      />,
    );
    expect(
      screen.getByRole("dialog", { name: "Daily research" }),
    ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "More actions" }),
    );
    expect(
      screen.getByRole("menuitem", { name: "Enable" }),
    ).toBeEnabled();
    await user.keyboard("{Escape}");
    view.rerender(<AutomationsPage {...defaults} payload={{ jobs: [] }} />);
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });
  it("omits protected system tasks without hiding user tasks and their original failure", async () => {
    const user = userEvent.setup();
    render(
      <AutomationsPage
        {...defaults}
        payload={{
          jobs: [
            job,
            { ...job, id: "heartbeat", name: "Heartbeat", protected: true },
            {
              ...job,
              id: "failed",
              name: "Failed task",
              state: {
                last_status: "error",
                last_error: "Remote disk is full",
              },
            },
          ],
        }}
      />,
    );
    await user.click(screen.getByRole("tab", { name: "Tasks" }));
    expect(
      screen.queryByRole("button", { name: /Heartbeat/ }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Failed task/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("Remote disk is full");
    expect(
      screen.getByRole("button", { name: "Run now" }),
    ).toBeEnabled();
  });
  it("creates an automation through the shared composer with the selected model ID", async () => {
    const user = userEvent.setup(),
      start = vi.fn().mockResolvedValue(true);
    render(
      <AutomationsPage
        {...defaults}
        settingsSnapshot={models}
        onStartChat={start}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Fast" }));
    const picker = await screen.findByRole("menu");
    await user.click(
      within(picker).getByRole("menuitemradio", { name: /^Deep/ }),
    );
    const input = screen.getByRole("textbox", {
      name: "Describe an automation",
    });
    await user.type(input, "Every Monday, review the project");
    await user.click(
      screen.getByRole("button", { name: "Send message" }),
    );
    expect(start).toHaveBeenCalledWith(
      "Every Monday, review the project",
      undefined,
      { intent: "create_automation" },
      "deep",
    );
    await waitFor(() => expect(input).toHaveValue(""));
  });
});

describe("Automation edit transaction", () => {
  it("preserves a draft across server refreshes and only patches changed fields", async () => {
    const user = userEvent.setup(),
      save = vi.fn();
    const view = render(
      <AutomationEditDialog
        job={job}
        saving={false}
        onOpenChange={vi.fn()}
        onSave={save}
      />,
    );
    const name = screen.getByRole("textbox", { name: /^Name/ });
    await user.clear(name);
    await user.type(name, "My revised task");
    const updated = {
      ...job,
      name: "Server name",
      payload: { message: "Updated by another client" },
      schedule: { kind: "every", every_ms: 7200_000 },
    };
    view.rerender(
      <AutomationEditDialog
        job={updated}
        saving={false}
        onOpenChange={vi.fn()}
        onSave={save}
      />,
    );
    expect(name).toHaveValue("My revised task");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(save).toHaveBeenCalledWith(updated, { name: "My revised task" });
  });
  it("retains the exact text after a rejected save and retries without rounding the interval", async () => {
    const user = userEvent.setup(),
      save = vi
        .fn()
        .mockRejectedValueOnce(new Error("Scheduler is unavailable"))
        .mockResolvedValue(undefined);
    render(
      <AutomationEditDialog
        job={job}
        saving={false}
        onOpenChange={vi.fn()}
        onSave={save}
      />,
    );
    const message = screen.getByRole("textbox", { name: /^Message/ });
    await user.clear(message);
    await user.type(message, "  Evidence:\nline two  ");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Scheduler is unavailable",
    );
    expect(message).toHaveValue("  Evidence:\nline two  ");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(save).toHaveBeenCalledTimes(2);
    expect(save.mock.calls[1][1]).toEqual({
      message: "  Evidence:\nline two  ",
    });
  });
  it("locks submission and cancellation while the write is pending", async () => {
    let complete!: () => void;
    const user = userEvent.setup(),
      save = vi.fn(
        () =>
          new Promise<void>((resolve) => {
            complete = resolve;
          }),
      ),
      close = vi.fn();
    render(
      <AutomationEditDialog
        job={job}
        saving={false}
        onOpenChange={close}
        onSave={save}
      />,
    );
    await user.type(screen.getByRole("textbox", { name: /^Name/ }), " revised");
    const submit = screen.getByRole("button", { name: "Save" });
    await user.dblClick(submit);
    expect(save).toHaveBeenCalledTimes(1);
    expect(submit).toHaveAttribute("aria-disabled", "true");
    expect(
      screen.getByRole("button", { name: "Cancel" }),
    ).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(close).not.toHaveBeenCalled();
    complete();
    await waitFor(() => expect(submit).toBeEnabled());
  });
});
