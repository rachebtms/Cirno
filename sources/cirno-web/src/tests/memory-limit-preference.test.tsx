import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryGraphLimit } from "@/features/memory/ui/MemoryGraphLimit";
import { usePreferences } from "@/hooks/usePreferences";
import { clearOwnerPreferences, connectPreferences, DEFAULT_OWNER_PREFERENCES, readOwnerPreferences, SNOW_THEME } from "@/features/preferences/store";

afterEach(clearOwnerPreferences);
function Control() {
  return <MemoryGraphLimit value={usePreferences().memoryGraphLimit ?? 300} />;
}
it("retains a failed limit draft and clears its error after a successful retry", async () => {
  const request = vi.fn().mockRejectedValueOnce(new Error("Disk is full")).mockResolvedValueOnce({
    revision: 1, values: { ...DEFAULT_OWNER_PREFERENCES, memoryGraphLimit: 600 }, themes: [SNOW_THEME],
  });
  const disconnect = connectPreferences({ requestMutation: request, onPreferencesUpdate: () => () => {}, onStatus: () => () => {} });
  try {
    render(<Control />);
    const input = screen.getByRole("spinbutton", { name: "Memory limit" });
    fireEvent.change(input, { target: { value: "600" } });
    fireEvent.blur(input);
    expect(await screen.findByText("Disk is full")).toBeVisible();
    expect(input).toHaveValue(600);
    expect(readOwnerPreferences().memoryGraphLimit).toBe(300);
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(readOwnerPreferences().memoryGraphLimit).toBe(600));
    expect(screen.queryByText("Disk is full")).not.toBeInTheDocument();
    expect(input).not.toHaveAttribute("aria-invalid", "true");
    expect(request).toHaveBeenCalledTimes(2);
    expect(request).toHaveBeenLastCalledWith("preferences.update", { patch: { memoryGraphLimit: 600 }, expected_revision: undefined });
  } finally { disconnect(); }
});
