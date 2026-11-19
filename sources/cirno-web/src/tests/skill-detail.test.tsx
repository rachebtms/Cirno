import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { SkillDetailDialog } from "@/features/skills/ui/SkillDetailDialog";
import { deleteSkill, fetchSkillDetail, updateSkillEnabled } from "@/lib/api";
import { copyTextToClipboard } from "@/lib/clipboard";
import type { SkillDetail } from "@/lib/contracts/skills";
import { ClientProvider } from "@/providers/ClientProvider";
import i18n from "@/i18n";

vi.mock("@/lib/api", () => ({
  fetchSkillDetail: vi.fn(), deleteSkill: vi.fn(), updateSkillEnabled: vi.fn(),
}));
vi.mock("@/lib/clipboard", () => ({ copyTextToClipboard: vi.fn() }));

const detail: SkillDetail = {
  name: "research", description: "Research tools", source: "home", enabled: true,
  available: false, unavailable_reason: "CLI: gh", raw_markdown: "Original research instructions",
  requirements: { bins: ["gh"], env: [], missing_bins: ["gh"], missing_env: [] },
  install_options: [{ id: "brew", kind: "brew", command: "brew install gh", label: "Install gh" }],
};

beforeEach(() => {
  vi.mocked(fetchSkillDetail).mockReset();
  vi.mocked(deleteSkill).mockReset();
  vi.mocked(updateSkillEnabled).mockReset();
  vi.mocked(copyTextToClipboard).mockReset();
});
afterEach(cleanup);

function renderDetail(value: SkillDetail) {
  vi.mocked(fetchSkillDetail).mockResolvedValue(value);
  render(<ClientProvider client={{} as never} token="fixture">
    <SkillDetailDialog skill={value} onClose={vi.fn()} />
  </ClientProvider>);
}

it("shows invalid metadata while keeping the original instructions readable", async () => {
  const error = "metadata.cirno.requires.bins: Input should be a valid list";
  renderDetail({ ...detail, unavailable_reason: error, requirements: null, install_options: [] });
  await screen.findByRole("switch");

  expect(screen.getByRole("alert")).toHaveTextContent(error);
  expect(screen.queryByText("Setup required")).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Skill instructions"));
  expect(screen.getByText("Original research instructions")).toBeVisible();
  expect(screen.getByText("Remove this Skill from Agent Home.")).toBeVisible();
});

it("reports a failed copy and clears the error after a successful retry", async () => {
  vi.mocked(copyTextToClipboard).mockResolvedValueOnce(false).mockResolvedValueOnce(true);
  renderDetail(detail);
  const button = await screen.findByRole("button", { name: "Copy command" });
  fireEvent.click(button);
  expect((await screen.findByText("Could not copy the command.")).closest('[role="alert"]')).toBeVisible();
  fireEvent.click(button);
  await waitFor(() => expect(screen.queryByText("Could not copy the command.")).not.toBeInTheDocument());
  expect(copyTextToClipboard).toHaveBeenNthCalledWith(2, "brew install gh");
});

it("cancels a deletion without writing and keeps a failed confirmation available for retry", async () => {
  renderDetail(detail);
  const remove = await screen.findByRole("button", { name: i18n.t("settings.skills.deleteAction") });
  await waitFor(() => expect(remove).toBeEnabled());
  fireEvent.click(remove);
  const first = await screen.findByRole("alertdialog");
  fireEvent.click(within(first).getByRole("button", { name: i18n.t("common.cancel") }));
  await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  expect(deleteSkill).not.toHaveBeenCalled();

  vi.mocked(deleteSkill).mockRejectedValueOnce(new Error("Skill directory is read-only"))
    .mockResolvedValueOnce({ skills: [], last_action: { name: detail.name, deleted: true, enabled: false } });
  fireEvent.click(remove);
  const confirmation = await screen.findByRole("alertdialog");
  fireEvent.click(within(confirmation).getByRole("button", { name: i18n.t("settings.skills.deleteConfirmAction") }));
  expect(await within(confirmation).findByRole("alert")).toHaveTextContent("Skill directory is read-only");
  fireEvent.click(within(confirmation).getByRole("button", { name: i18n.t("settings.skills.deleteConfirmAction") }));
  await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  expect(deleteSkill).toHaveBeenCalledTimes(2);
});
