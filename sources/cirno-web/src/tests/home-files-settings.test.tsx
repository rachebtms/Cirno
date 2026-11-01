import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { HomeFilesSettings } from "@/components/settings/capabilities/HomeFilesSettings";
import type { CirnoClient } from "@/lib/cirno-client";

it("edits a Home file through the revision-aware settings operation", async () => {
  const requestMutation = vi.fn(async (action: string, data: Record<string, string>) => action === "settings.profile.read"
    ? { name: data.name, file: `${data.name}.md`, content: "Existing content", revision: "before" }
    : { name: data.name, file: `${data.name}.md`, content: data.content, revision: "after" });
  render(<HomeFilesSettings section="personality" client={{ requestMutation } as unknown as CirnoClient} />);
  fireEvent.click(await screen.findByRole("button", { name: "Edit Personality" }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Be concise." } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(requestMutation).toHaveBeenCalledWith("settings.profile.update", {
    name: "soul", content: "Be concise.", revision: "before",
  }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

it("keeps an unsaved edit open when the Home file changed elsewhere", async () => {
  const requestMutation = vi.fn(async (action: string, data: Record<string, string>) => {
    if (action === "settings.profile.update") throw new Error("This Home file changed. Reload it before saving.");
    return { name: data.name, file: `${data.name}.md`, content: "Existing content", revision: "before" };
  });
  render(<HomeFilesSettings section="personality" client={{ requestMutation } as unknown as CirnoClient} />);
  fireEvent.click(await screen.findByRole("button", { name: "Edit Personality" }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Unsaved edit" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("This Home file changed");
  expect(screen.getByRole("textbox")).toHaveValue("Unsaved edit");
});

it("opens the personality navigation section with only its own Home files", async () => {
  const { renderSettingsView, settingsPayload, jsonResponse } = await import("@/tests/settings-test-utils");
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => jsonResponse(String(input) === "/api/settings" ? settingsPayload() : { apps: [], presets: [], features: [] })));
  const requestMutation = vi.fn(async (_action: string, data: Record<string, string>) => ({
    name: data.name, file: `${data.name}.md`, content: "Home content", revision: "current",
  }));
  renderSettingsView({ initialSection: "personality", initialSettings: settingsPayload(), client: {
    requestMutation, status: "open", onStatus: () => () => {},
  } as unknown as CirnoClient });
  expect(await screen.findByRole("button", { name: "Edit Personality" })).toBeVisible();
  expect(requestMutation).toHaveBeenCalledWith("settings.profile.read", { name: "soul" });
  expect(requestMutation).not.toHaveBeenCalledWith("settings.profile.read", { name: "memory" });
  expect(screen.queryByRole("button", { name: "Edit Long-term memory" })).not.toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Search memories" })).not.toBeInTheDocument();
});

it("keeps the long-term memory editor separate from personality files", async () => {
  const requestMutation = vi.fn(async (_action: string, data: Record<string, string>) => ({
    name: data.name, file: `${data.name}.md`, content: "Existing memory", revision: "current",
  }));
  render(<HomeFilesSettings section="memory" client={{ requestMutation } as unknown as CirnoClient} />);
  expect(await screen.findByRole("button", { name: "Edit Long-term memory" })).toBeVisible();
  expect(requestMutation).toHaveBeenCalledTimes(1);
  expect(requestMutation).toHaveBeenCalledWith("settings.profile.read", { name: "memory" });
  expect(screen.queryByRole("button", { name: "Edit Personality" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Edit Long-term memory" }));
  expect(screen.getByRole("textbox")).toHaveValue("Existing memory");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Updated memory" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(requestMutation).toHaveBeenCalledWith("settings.profile.update", {
    name: "memory", content: "Updated memory", revision: "current",
  }));
});
