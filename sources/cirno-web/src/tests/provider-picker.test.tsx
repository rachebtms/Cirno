import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import {
  requestMutationMock,
  settingsPayload,
  installSettingsViewTestHooks,
} from "@/tests/settings-test-utils";
import { renderProviderManager } from "./helpers/settings-providers";

describe("Settings providers", () => {
  installSettingsViewTestHooks();
  it("searches provider aliases and configures in the same dialog without adding an unsaved row", async () => {
    const user = userEvent.setup();
    const payload = settingsPayload();
    payload.providers = [
      { id: "deepseek", name: "DeepSeek", configured: true },
      { id: "volcengine", name: "VolcEngine", configured: false },
      { id: "volcengine_coding_plan", name: "VolcEngine Coding Plan", configured: false },
    ];
    renderProviderManager({ initialSection: "models", initialSettings: payload });
    const trigger = screen.getByRole("button", { name: "Add provider" });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Add provider" });
    const search = within(dialog).getByRole("searchbox", { name: "Search providers" });
    await user.click(search);
    expect(within(dialog).queryByRole("option", { name: "DeepSeek" })).not.toBeInTheDocument();
    await user.type(search, "火山");
    expect(within(dialog).getAllByRole("option")).toHaveLength(2);
    await user.keyboard("{ArrowDown}{End}{Enter}");
    expect(screen.getByRole("dialog", { name: "VolcEngine Coding Plan" })).toBe(dialog);
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(within(dialog).getByLabelText("API key", { selector: "input" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "VolcEngine Coding Plan" }),
    ).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Back to providers" }));
    expect(screen.getByRole("dialog", { name: "Add provider" })).toBe(dialog);
    expect(screen.getByRole("searchbox", { name: "Search providers" })).toHaveValue("火山");
    await user.keyboard("{Escape}{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("region", { name: "Providers" })).toBeVisible());
    await waitFor(() => expect(screen.getByRole("button", { name: "Add provider" })).toHaveFocus());
    expect(requestMutationMock).not.toHaveBeenCalled();
  });

  it("keeps custom provider creation available for empty searches and discards cancelled drafts", async () => {
    const user = userEvent.setup();
    renderProviderManager({ initialSection: "models", initialSettings: settingsPayload() });
    await user.click(screen.getByRole("button", { name: "Add provider" }));
    await user.type(screen.getByRole("searchbox", { name: "Search providers" }), "does-not-exist");
    expect(screen.getByRole("status")).toHaveTextContent("No providers match this search.");
    await user.click(screen.getByRole("button", { name: "Custom" }));
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    await user.type(screen.getByPlaceholderText("My model provider"), "Unsaved gateway");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Add provider" }));
    expect(screen.getByRole("searchbox", { name: "Search providers" })).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Custom" }));
    expect(screen.getByPlaceholderText("My model provider")).toHaveValue("");
    expect(requestMutationMock).not.toHaveBeenCalled();
  });

  it("keeps provider setup accessible on mobile without opening the keyboard immediately", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({
        matches: query === "(max-width: 639px)",
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    renderProviderManager({ initialSection: "models", initialSettings: settingsPayload() });
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));
    const dialog = screen.getByRole("dialog", { name: "Add provider" });
    expect(dialog).toBeVisible();
    expect(screen.getByRole("searchbox", { name: "Search providers" })).not.toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    expect(screen.getByRole("dialog", { name: "Custom" })).toBe(dialog);
  });
});
