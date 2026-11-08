import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useFileEditDisplayMode } from "@/hooks/useFileEditDisplayMode";
import {
  DEFAULT_PREFERENCES,
  clearOwnerPreferences,
  writePreferences,
} from "@/features/preferences/store";

function DisplayModeProbe() {
  const mode = useFileEditDisplayMode();
  return <div data-testid="mode">{mode}</div>;
}

describe("useFileEditDisplayMode", () => {
  afterEach(() => {
    clearOwnerPreferences();
  });

  it("updates when local preferences change in the same document", async () => {
    render(<DisplayModeProbe />);

    expect(screen.getByTestId("mode")).toHaveTextContent("summary");

    act(() => {
      writePreferences({
        ...DEFAULT_PREFERENCES,
        fileEditDisplayMode: "diff",
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId("mode")).toHaveTextContent("diff");
    });
  });
});
