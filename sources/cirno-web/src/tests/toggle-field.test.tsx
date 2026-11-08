import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, it } from "vitest";
import { ToggleField } from "@/ui/fields/ToggleField";
it("toggles by its visible label and keyboard and keeps its explanation associated", async () => {
  const user = userEvent.setup();
  function Field() { const [selected, setSelected] = useState(false); return <ToggleField label="Use proxy" description="Use the configured proxy." selected={selected} onChange={setSelected} />; }
  render(<Field />);
  const control = screen.getByRole("switch", { name: "Use proxy" });
  expect(control).toHaveAccessibleDescription("Use the configured proxy.");
  await user.click(screen.getByText("Use proxy", { exact: true }));
  expect(control).toBeChecked();
  control.focus(); await user.keyboard(" "); expect(control).not.toBeChecked();
});
