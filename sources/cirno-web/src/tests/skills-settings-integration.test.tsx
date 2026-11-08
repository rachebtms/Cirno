import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { SkillsLibrary } from "@/features/skills/SkillsLibrary";
import { ClientProvider } from "@/providers/ClientProvider";
import { installSettingsViewTestHooks, jsonResponse, renderSettingsView } from "./settings-test-utils";
installSettingsViewTestHooks();
it("shows available skills while the unrelated settings snapshot is still pending", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => {})),
  );
  renderSettingsView({
    initialSection: "skills",
    initialSettings: null,
    showSidebar: false,
    skills: [
      {
        name: "project-review",
        description: "Review a project.",
        source: "builtin",
        available: true,
        enabled: true,
      },
    ],
  });
  expect(screen.getByRole("button", { name: "Open details for project-review" })).toBeVisible();
  expect(screen.getByRole("textbox", { name: "Search installed skills" })).toBeVisible();
});

it("loads only the skill detail body and preserves it while checking dependencies again", async () => {
  const skill = {
    name: "pr-review",
    description: "Review pull requests",
    source: "builtin",
    available: false,
    enabled: true,
  };
  let finish!: (response: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    ),
  );
  render(
    <ClientProvider client={{} as never} token="tok">
      <SkillsLibrary skills={[skill]} />
    </ClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Open details for pr-review" }));
  const detail = screen.getByRole("dialog");
  expect(within(detail).getByText("Review pull requests")).toBeVisible();
  expect(within(detail).getByRole("status", { name: "Loading skill details..." })).toHaveAttribute(
    "aria-busy",
    "true",
  );
  await act(async () =>
    finish(
      jsonResponse({
        ...skill,
        raw_markdown: "Review repository changes.",
        requirements: {
          bins: ["gh"],
          env: [],
          missing_bins: ["gh"],
          missing_env: [],
        },
      }),
    ),
  );
  const toggle = within(detail).getByRole("switch");
  expect(within(detail).getByText("Skill instructions")).toBeVisible();
  let fail!: (error: Error) => void;
  vi.mocked(fetch).mockImplementationOnce(
    () =>
      new Promise((_, reject) => {
        fail = reject;
      }),
  );
  fireEvent.click(within(detail).getByRole("button", { name: "Check again" }));
  expect(within(detail).getByText("Skill instructions")).toBeVisible();
  expect(toggle).toBeDisabled();
  expect(within(detail).queryByRole("status", { name: "Loading skill details..." })).not.toBeInTheDocument();
  await act(async () => fail(new Error("Read failed")));
  expect(within(detail).getByRole("alert")).toHaveTextContent("Read failed");
  expect(within(detail).getByRole("button", { name: "Retry" })).toBeEnabled();
  expect(within(detail).getByText("Skill instructions")).toBeVisible();
  expect(toggle).toBeEnabled();
});

it("keeps skill group labels natural without changing grouping or filtering", () => {
  render(
    <ClientProvider client={{} as never} token="tok">
      <SkillsLibrary
        skills={[
          { name: "pr-review", description: "Review pull requests", source: "home", available: true },
          { name: "cron", description: "Schedule reminders", source: "builtin", available: true },
          { name: "team-guide", description: "Team conventions", source: "team", available: true },
        ]}
      />
    </ClientProvider>,
  );
  for (const name of ["Custom", "Built-in", "Other"]) {
    const title = screen.getByRole("heading", { name: new RegExp(`${name} 1`) });
    expect(title).toBeVisible();
  }
  fireEvent.change(screen.getByRole("textbox", { name: "Search installed skills" }), {
    target: { value: "cron" },
  });
  expect(screen.queryByRole("heading", { name: /Custom 1/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: /Other 1/ })).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /Built-in 1/ })).toBeVisible();
  expect(screen.getByRole("button", { name: "Open details for cron" })).toBeVisible();
});
