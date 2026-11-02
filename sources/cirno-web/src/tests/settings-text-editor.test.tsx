import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsTextEditor } from "@/components/settings/shared/SettingsTextEditor";
import i18n from "@/i18n";

beforeEach(async () => { await i18n.changeLanguage("en"); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("settings text editor copy", () => {
  it.each([undefined, "", "  ", "Headers", " Headers "])(
    "does not repeat its title as a description (%s)", async (description) => {
      const warning = vi.spyOn(console, "warn");
      render(<SettingsTextEditor title="Headers" description={description} value="{}" onSave={vi.fn()} />);
      fireEvent.click(screen.getByRole("button", { name: "Headers" }));
      const dialog = await screen.findByRole("dialog", { name: "Headers" });
      expect(within(dialog).getAllByText("Headers")).toHaveLength(1);
      expect(dialog).not.toHaveAttribute("aria-describedby");
      expect(dialog).toHaveAccessibleDescription("");
      expect(within(dialog).getByRole("textbox", { name: "Headers" })).toHaveValue("{}");
      expect(within(dialog).getByRole("textbox", { name: "Headers" })).toHaveFocus();
      expect(warning).not.toHaveBeenCalled();
    },
  );

  it("keeps meaningful help associated with the dialog and saves edited values", async () => {
    const warning = vi.spyOn(console, "warn");
    const save = vi.fn();
    const help = "Use a JSON object for additional request headers.";
    render(<SettingsTextEditor title="Headers" description={help} value="{}" onSave={save} />);
    fireEvent.click(screen.getByRole("button", { name: "Headers" }));
    const dialog = await screen.findByRole("dialog", { name: "Headers" });
    expect(dialog).toHaveAccessibleDescription(help);
    expect(within(dialog).getAllByText(help)).toHaveLength(1);
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Headers" }), { target: { value: '{"Accept":"application/json"}' } });
    fireEvent.click(within(dialog).getByRole("button", { name: i18n.t("settings.actions.save") }));
    expect(save).toHaveBeenCalledWith('{"Accept":"application/json"}');
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(warning).not.toHaveBeenCalled();
  });
});

describe("JSON configuration editing", () => {
  it("pretty-prints on open and save, formats drafts, and keeps malformed JSON visible", async () => {
    const save = vi.fn();
    render(<SettingsTextEditor title="MCP JSON" value={'{"args":["-y","docs-mcp"]}'} json onSave={save} />);
    fireEvent.click(screen.getByRole("button", { name: "MCP JSON" }));
    const editor = screen.getByRole("textbox", { name: "MCP JSON" });
    expect(editor).toHaveValue(JSON.stringify({ args: ["-y", "docs-mcp"] }, null, 2));
    fireEvent.change(editor, { target: { value: '{"command":' } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("alert");
    expect(save).not.toHaveBeenCalled();
    expect(editor).toHaveValue('{"command":');
    fireEvent.change(editor, { target: { value: '{"command":"node"}' } });
    fireEvent.click(screen.getByRole("button", { name: "Format JSON" }));
    expect(editor).toHaveValue(JSON.stringify({ command: "node" }, null, 2));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(save).toHaveBeenCalledWith(JSON.stringify({ command: "node" }, null, 2)));
  });

  it("loads configuration on demand and prevents saving a failed read", async () => {
    const load = vi.fn().mockRejectedValue(new Error("Configuration unavailable"));
    const save = vi.fn();
    render(<SettingsTextEditor title="MCP JSON" value="" json loadValue={load} onSave={save} />);
    expect(load).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "MCP JSON" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Configuration unavailable");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(save).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    load.mockResolvedValueOnce('{"command":"node"}');
    fireEvent.click(screen.getByRole("button", { name: "MCP JSON" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "MCP JSON" })).toHaveValue(JSON.stringify({ command: "node" }, null, 2)));
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });
});
