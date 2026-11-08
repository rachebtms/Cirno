import { ModelSetup } from "@/features/entry/ModelSetup";
import type { SettingsSectionKey } from "@/features/settings/contracts";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

vi.mock("@/features/settings/SettingsView", () => ({
  SettingsView: ({
    initialSection,
    onSectionChange,
  }: {
    initialSection: SettingsSectionKey;
    onSectionChange: (section: SettingsSectionKey) => void;
  }) => (
    <div data-testid="setup-section">
      {initialSection}
      <button onClick={() => onSectionChange("providers")}>Connect provider</button>
    </div>
  ),
}));

it("keeps Provider and Models navigation available after connecting a provider", async () => {
  const user = userEvent.setup();
  render(<ModelSetup onComplete={vi.fn()} onModelNameChange={vi.fn()} />);
  expect(await screen.findByTestId("setup-section")).toHaveTextContent("providers");
  await user.click(screen.getByRole("tab", { name: "Models" }));
  expect(screen.getByTestId("setup-section")).toHaveTextContent("models");
  await user.click(screen.getByRole("button", { name: "Connect provider" }));
  expect(screen.getByTestId("setup-section")).toHaveTextContent("providers");
  await user.click(screen.getByRole("tab", { name: "Models" }));
  expect(screen.getByTestId("setup-section")).toHaveTextContent("models");
  expect(screen.getByRole("tab", { name: "Providers" })).toBeEnabled();
});
