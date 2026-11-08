import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProfileFiles } from "@/features/profile/ProfileFiles";
import type { WebUIMutationTransport } from "@/lib/api";
const file = (name: string, revision = "v1", content = "Original text") => ({
  name,
  file: `${name}.md`,
  revision,
  content,
});
const transport = (requestMutation: unknown) => ({ requestMutation }) as WebUIMutationTransport;
describe("profile files", () => {
  it("loads files independently and exposes an individual read failure", async () => {
    const request = vi.fn(async (_method, { name }) => {
      if (name === "soul") throw new Error("SOUL.md is unreadable");
      return file(name);
    });
    render(<ProfileFiles client={transport(request)} section="personality" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("SOUL.md is unreadable");
    expect(await screen.findByRole("button", { name: "Edit Conversation personality" })).toBeEnabled();
    expect(request).toHaveBeenCalledTimes(4);
  });
  it("saves the revision loaded for this opening after the displayed file is refreshed", async () => {
    const user = userEvent.setup();
    let reads = 0;
    const request = vi.fn(async (method, { name, ...values }) =>
      method === "settings.profile.read"
        ? file(name, `v${++reads}`, `Content ${reads}`)
        : file(name, "v4", values.content),
    );
    render(<ProfileFiles client={transport(request)} section="memory" />);
    await user.click(await screen.findByRole("button", { name: /Edit/ }));
    const input = await screen.findByRole("textbox");
    await waitFor(() => expect(input).toHaveValue("Content 2"));
    // Refresh can also be triggered by a parent event while its modal owns focus.
    await act(async () => screen.getByRole("button", { name: /Reload/, hidden: true }).click());
    await user.clear(input);
    await user.type(input, "My draft");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("settings.profile.update", {
        name: "memory",
        content: "My draft",
        revision: "v2",
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
  it("preserves the draft and displays a save conflict", async () => {
    const user = userEvent.setup();
    const request = vi.fn(async (method, { name }) => {
      if (method === "settings.profile.update") throw new Error("File changed; reload before saving");
      return file(name);
    });
    render(<ProfileFiles client={transport(request)} section="memory" />);
    await user.click(await screen.findByRole("button", { name: /Edit/ }));
    const input = await screen.findByRole("textbox");
    await waitFor(() => expect(input).toBeEnabled());
    await user.clear(input);
    await user.type(input, "Unsaved research notes");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("File changed; reload before saving");
    expect(input).toHaveValue("Unsaved research notes");
    expect(screen.getByRole("dialog")).toBeVisible();
  });
});
