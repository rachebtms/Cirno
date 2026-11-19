import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ThemeSettings } from "@/features/preferences/ThemeSettings";
import {
  clearOwnerPreferences, connectPreferences, DEFAULT_OWNER_PREFERENCES, receivePreferences,
  SNOW_THEME, type PreferencesConnection, type PreferencesSnapshot,
} from "@/features/preferences/store";

afterEach(() => { cleanup(); clearOwnerPreferences(); });

function setup() {
  const original = { ...SNOW_THEME, id: "custom-a", name: "Original theme" };
  let server: PreferencesSnapshot = {
    revision: 1, values: { ...DEFAULT_OWNER_PREFERENCES, themeId: original.id, customThemes: [original] }, themes: [SNOW_THEME],
  };
  receivePreferences(server);
  const request = vi.fn<PreferencesConnection["requestMutation"]>().mockImplementation(async (_action, payload) => {
    if (payload.expected_revision !== undefined && payload.expected_revision !== server.revision) throw new Error("Fixture revision conflict");
    server = { ...server, revision: server.revision + 1, values: { ...server.values, ...payload.patch as object } };
    return server;
  });
  const disconnect = connectPreferences({ requestMutation: request, onStatus: () => () => {}, onPreferencesUpdate: () => () => {} });
  render(<ThemeSettings />);
  fireEvent.click(screen.getByRole("button", { name: "Edit theme" }));
  fireEvent.change(screen.getByLabelText("Theme name"), { target: { value: "Local draft" } });
  return { request, disconnect, snapshot: () => server, receive: (next: PreferencesSnapshot) => { server = next; receivePreferences(next); } };
}

it.each([false, true])("saves against the editor's source theme list (remote theme conflict: %s)", async conflict => {
  const owner = setup();
  try {
    act(() => {
      const current = owner.snapshot();
      owner.receive({ ...current, revision: 2, values: {
        ...current.values, language: "en", codeWrap: false,
        customThemes: conflict ? [{ ...current.values.customThemes[0], name: "Other device theme" }] : current.values.customThemes,
      } });
    });
    fireEvent.click(screen.getByRole("button", { name: "Save theme" }));
    if (conflict) {
      await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/changed/i));
      expect(owner.request).not.toHaveBeenCalled();
      expect(screen.getByLabelText("Theme name")).toHaveValue("Local draft");
    } else {
      await waitFor(() => expect(screen.queryByLabelText("Theme name")).not.toBeInTheDocument());
      expect(owner.request).toHaveBeenCalledWith("preferences.update", expect.objectContaining({ expected_revision: 2 }));
    }
  } finally { owner.disconnect(); }
});

it("locks editor replacement and theme removal until its save settles", async () => {
  const owner = setup();
  let finish!: (snapshot: PreferencesSnapshot) => void;
  owner.request.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  try {
    fireEvent.click(screen.getByRole("button", { name: "Save theme" }));
    expect(screen.getByRole("button", { name: "Create theme" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Edit theme" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remove theme" })).toBeDisabled();
    await act(async () => { finish({ ...owner.snapshot(), revision: 2 }); });
    expect(screen.getByRole("button", { name: "Create theme" })).toBeEnabled();
  } finally {
    await act(async () => { finish?.({ ...owner.snapshot(), revision: 2 }); });
    owner.disconnect();
  }
});

it("retains a rejected draft and unlocks it for correction", async () => {
  const owner = setup();
  owner.request.mockRejectedValueOnce(new Error("Fixture save failure"));
  try {
    fireEvent.click(screen.getByRole("button", { name: "Save theme" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Fixture save failure"));
    expect(screen.getByLabelText("Theme name")).toHaveValue("Local draft");
    expect(screen.getByRole("button", { name: "Save theme" })).toBeEnabled();
  } finally { owner.disconnect(); }
});
