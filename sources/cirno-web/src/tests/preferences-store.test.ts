import { beforeEach, describe, expect, it, vi } from "vitest";
import { CirnoClient } from "@/lib/cirno-client";
import { clearOwnerPreferences, connectPreferences, DEFAULT_OWNER_PREFERENCES,
  patchPreferences, readOwnerPreferences, readPreferenceStatus, receivePreferences,
  SNOW_THEME, type PreferencesSnapshot } from "@/features/preferences/store";

function snapshot(revision = 0, values = DEFAULT_OWNER_PREFERENCES): PreferencesSnapshot {
  return { revision, values, themes: [SNOW_THEME] };
}
function connection() {
  const client = new CirnoClient({ url: "ws://localhost/v0/ws" });
  let update!: (next: PreferencesSnapshot) => void;
  let status!: (state: "open") => void;
  vi.spyOn(client, "onPreferencesUpdate").mockImplementation(handler => { update = handler; return () => {}; });
  vi.spyOn(client, "onStatus").mockImplementation(handler => { status = handler; return () => {}; });
  const request = vi.spyOn(client, "requestMutation");
  return { client, request, update: (next: PreferencesSnapshot) => update(next), open: () => status("open") };
}

describe("server-owned presentation preferences", () => {
  beforeEach(() => { clearOwnerPreferences(); vi.restoreAllMocks(); });

  it("starts with the paired Snow theme without browser persistence", () => {
    expect(readOwnerPreferences().themeId).toBe("cirno-snow");
    const write = vi.spyOn(Storage.prototype, "setItem");
    void patchPreferences({ themeMode: "dark" });
    expect(readOwnerPreferences().themeMode).toBe("dark");
    expect(write).not.toHaveBeenCalled();
  });

  it("queues disconnected edits and acknowledges the server save", async () => {
    const pending = patchPreferences({ themeMode: "dark" });
    const remote = connection();
    remote.request.mockResolvedValue(snapshot(1, { ...DEFAULT_OWNER_PREFERENCES, themeMode: "dark" }));
    const disconnect = connectPreferences(remote.client);
    expect(await pending).toBe(true);
    expect(remote.request).toHaveBeenCalledWith("preferences.update", { patch: { themeMode: "dark" }, expected_revision: undefined });
    disconnect();
  });

  it("rebases queued local edits on newer device updates", () => {
    void patchPreferences({ codeWrap: false });
    receivePreferences(snapshot(4, { ...DEFAULT_OWNER_PREFERENCES, language: "fr" }));
    expect(readOwnerPreferences()).toMatchObject({ codeWrap: false, language: "fr" });
    receivePreferences(snapshot(3));
    expect(readOwnerPreferences().language).toBe("fr");
  });

  it("rolls back a rejected theme save and continues unrelated queued changes", async () => {
    const first = patchPreferences({ themeMode: "dark" });
    const second = patchPreferences({ codeWrap: false });
    const remote = connection();
    remote.request.mockRejectedValueOnce(new Error("Connection rejected save"))
      .mockResolvedValueOnce(snapshot(1, { ...DEFAULT_OWNER_PREFERENCES, codeWrap: false }));
    const disconnect = connectPreferences(remote.client);
    expect(await first).toBe(false);
    expect(await second).toBe(true);
    expect(readOwnerPreferences()).toMatchObject({ themeMode: "system", codeWrap: false });
    expect(readPreferenceStatus().error).toBe("Connection rejected save");
    disconnect();
  });

  it("ignores old in-flight reads and events after sign-out", async () => {
    const remote = connection();
    let complete!: (snapshot: PreferencesSnapshot) => void;
    remote.request.mockReturnValue(new Promise(resolve => { complete = resolve; }));
    const disconnect = connectPreferences(remote.client);
    remote.open();
    clearOwnerPreferences();
    complete(snapshot(7, { ...DEFAULT_OWNER_PREFERENCES, themeMode: "dark" }));
    remote.update(snapshot(8, { ...DEFAULT_OWNER_PREFERENCES, language: "fr" }));
    await Promise.resolve();
    expect(readOwnerPreferences()).toEqual(DEFAULT_OWNER_PREFERENCES);
    disconnect();
  });
});
