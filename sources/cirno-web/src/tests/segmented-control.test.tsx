import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { SegmentedControl } from "@/components/ui/segmented-control";
function Example({ mode = "buttons" }: { mode?: "buttons" | "tabs" | "radio" }) {
  const [value, setValue] = useState("all");
  return <SegmentedControl value={value} mode={mode} onChange={setValue} ariaLabel="Notifications"
    options={[{ value: "all", label: "All" }, { value: "operations", label: "Actions · 1" }, { value: "conversations", label: "Reports · 11" }, { value: "system", label: "System" }]} />;
}
describe("shared selection controls", () => {
  it("selects differently sized inbox categories without a scaled indicator", async () => {
    const user = userEvent.setup();
    const { container } = render(<Example mode="tabs" />);
    for (const name of ["Actions · 1", "Reports · 11", "System", "All"]) {
      const tab = screen.getByRole("tab", { name });
      await user.click(tab);
      expect(tab).toHaveAttribute("aria-selected", "true");
    }
    expect(container.querySelector('[style*="scale:"]')).toBeNull();
  });
  it("supports keyboard navigation through tabs", async () => {
    const user = userEvent.setup();
    render(<Example mode="tabs" />);
    screen.getByRole("tab", { name: "All" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Actions · 1" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Actions · 1" })).toHaveAttribute("aria-selected", "true");
  });
  it("selects radio values with arrow keys and keeps the selected value on focus return", async () => {
    const user = userEvent.setup();
    render(<Example mode="radio" />);
    screen.getByRole("radio", { name: "All" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Actions · 1" })).toHaveFocus();
    expect(screen.getByRole("radio", { name: "Actions · 1" })).toBeChecked();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "All" })).toBeChecked();
  });
  it("retains a selection when the selected option is clicked again", async () => {
    const user = userEvent.setup();
    render(<Example />);
    const option = screen.getByRole("button", { name: "All" });
    await user.click(option);
    expect(option).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "System" }));
    expect(screen.getByRole("button", { name: "System" })).toHaveAttribute("aria-pressed", "true");
  });
});
