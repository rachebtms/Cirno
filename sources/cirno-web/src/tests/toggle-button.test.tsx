import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ToggleButton } from "@/components/ui/toggle-button";

describe("ToggleButton", () => {
  it("reports user changes while rendering the controlled selection", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ToggleButton checked label="Feature" onChange={onChange} />,
    );
    const toggle = screen.getByRole("switch", { name: "Feature" });
    expect(toggle).toBeChecked();

    fireEvent.click(toggle);
    expect(onChange).toHaveBeenLastCalledWith(false);
    rerender(<ToggleButton checked={false} label="Feature" onChange={onChange} />);
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenLastCalledWith(true);
  });

  it.each([false, true])("does not toggle while disabled (checked=%s)", (checked) => {
    const onChange = vi.fn();
    render(<ToggleButton checked={checked} disabled label="Feature" onChange={onChange} />);
    const toggle = screen.getByRole("switch", { name: "Feature" });
    expect(toggle).toBeDisabled();
    fireEvent.click(toggle);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("keeps accessible labeling and keyboard activation without submitting the form", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onSubmit = vi.fn((event) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <p id="toggle-help">Enable this feature.</p>
        <ToggleButton
          id="feature-toggle"
          checked={false}
          label="Feature"
          ariaLabel="Enable feature"
          aria-describedby="toggle-help"
          aria-invalid
          onChange={onChange}
        />
      </form>,
    );
    const toggle = screen.getByRole("switch", { name: "Enable feature" });
    expect(toggle).toHaveAttribute("id", "feature-toggle");
    expect(toggle).toHaveAccessibleDescription("Enable this feature.");
    expect(toggle).toHaveAttribute("aria-invalid", "true");
    await user.tab();
    expect(toggle).toHaveFocus();
    await user.keyboard(" ");
    expect(onChange.mock.calls).toEqual([[true]]);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
