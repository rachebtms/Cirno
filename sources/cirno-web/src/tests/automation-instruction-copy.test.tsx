import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { TaskInstructions } from "@/features/automations/detail/TaskInstructions";
import i18n from "@/i18n";
import { copyTextToClipboard } from "@/lib/clipboard";
import type { SessionAutomationJob } from "@/lib/contracts/automations";

vi.mock("@/lib/clipboard", () => ({ copyTextToClipboard: vi.fn() }));
const copy = vi.mocked(copyTextToClipboard);
const job: SessionAutomationJob = {
  id: "fixture", name: "Fixture", enabled: true, kind: "local_trigger",
  schedule: { kind: "local" }, payload: { message: "", command: "old-command" }, state: {},
};
const nextJob = { ...job, payload: { ...job.payload, command: "new-command" } };

beforeEach(async () => {
  copy.mockReset();
  await i18n.changeLanguage("en");
});

it("does not report a changed command as copied", async () => {
  copy.mockResolvedValue(true);
  const { rerender } = render(<TaskInstructions job={job} />);
  await act(async () => fireEvent.click(screen.getByRole("button")));
  expect(screen.getByRole("button")).toHaveTextContent(i18n.t("settings.automations.commandCopied"));
  rerender(<TaskInstructions job={nextJob} />);
  expect(screen.getByRole("button")).toHaveTextContent(i18n.t("settings.automations.copyCommand"));
});

it("ignores an old copy completion after the command changes", async () => {
  let finish!: (value: boolean) => void;
  copy.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const { rerender } = render(<TaskInstructions job={job} />);
  fireEvent.click(screen.getByRole("button"));
  rerender(<TaskInstructions job={nextJob} />);
  await act(async () => finish(true));
  expect(copy).toHaveBeenCalledWith("old-command");
  expect(screen.getByRole("button")).toHaveTextContent(i18n.t("settings.automations.copyCommand"));
});

it("keeps the latest successful copy when an earlier request settles later", async () => {
  let finish!: (value: boolean) => void;
  copy.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
    .mockResolvedValueOnce(true);
  const { rerender } = render(<TaskInstructions job={job} />);
  fireEvent.click(screen.getByRole("button"));
  rerender(<TaskInstructions job={nextJob} />);
  await act(async () => fireEvent.click(screen.getByRole("button")));
  await act(async () => finish(true));
  expect(copy.mock.calls).toEqual([["old-command"], ["new-command"]]);
  expect(screen.getByRole("button")).toHaveTextContent(i18n.t("settings.automations.commandCopied"));
});
