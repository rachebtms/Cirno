import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ProfileFiles } from "@/features/profile/ProfileFiles";
import type { CirnoClient } from "@/lib/cirno-client";

it("opens the personality navigation section with only its own Home files", async () => {
  const { renderSettingsView, settingsPayload, jsonResponse } = await import("@/tests/settings-test-utils");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) =>
      jsonResponse(
        String(input) === "/v0/settings" ? settingsPayload() : { apps: [], presets: [], features: [] },
      ),
    ),
  );
  const requestMutation = vi.fn(async (_action: string, data: Record<string, string>) => ({
    name: data.name,
    file: `${data.name}.md`,
    content: "Home content",
    revision: "current",
  }));
  renderSettingsView({
    initialSection: "personality",
    initialSettings: settingsPayload(),
    client: {
      requestMutation,
      status: "open",
      onStatus: () => () => {},
    } as unknown as CirnoClient,
  });
  expect(await screen.findByRole("button", { name: "Edit Router personality" })).toBeVisible();
  expect(requestMutation).toHaveBeenCalledWith("settings.profile.read", { name: "soul" });
  expect(requestMutation).not.toHaveBeenCalledWith("settings.profile.read", { name: "memory" });
  expect(screen.queryByRole("button", { name: "Edit Long-term memory" })).not.toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Search memories" })).not.toBeInTheDocument();
});

it("keeps the long-term memory editor separate from personality files", async () => {
  const requestMutation = vi.fn(async (_action: string, data: Record<string, string>) => ({
    name: data.name,
    file: `${data.name}.md`,
    content: "Existing memory",
    revision: "current",
  }));
  render(<ProfileFiles section="memory" client={{ requestMutation } as unknown as CirnoClient} />);
  expect(await screen.findByRole("button", { name: "Edit Long-term memory" })).toBeVisible();
  expect(requestMutation).toHaveBeenCalledTimes(1);
  expect(requestMutation).toHaveBeenCalledWith("settings.profile.read", { name: "memory" });
  expect(screen.queryByRole("button", { name: "Edit Router personality" })).not.toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Edit Long-term memory" }));
  const input = screen.getByRole("textbox");
  await waitFor(() => expect(input).toBeEnabled());
  expect(input).toHaveValue("Existing memory");
  await user.clear(input);
  await user.type(input, "Updated memory");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(requestMutation).toHaveBeenCalledWith("settings.profile.update", {
      name: "memory",
      content: "Updated memory",
      revision: "current",
    }),
  );
});
