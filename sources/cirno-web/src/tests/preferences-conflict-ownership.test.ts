import { afterEach, expect, it, vi } from "vitest";
import {
  clearOwnerPreferences, connectPreferences, DEFAULT_OWNER_PREFERENCES,
  patchPreferences, readOwnerPreferences, readPreferenceStatus, receivePreferences, SNOW_THEME,
  type PreferencesConnection, type PreferencesSnapshot,
} from "@/features/preferences/store";

afterEach(clearOwnerPreferences);

function snapshot(revision: number, values = DEFAULT_OWNER_PREFERENCES): PreferencesSnapshot {
  return { revision, values, themes: [SNOW_THEME] };
}
const themeA = { ...SNOW_THEME, id: "custom-a", name: "Theme A" };
const themeB = { ...SNOW_THEME, id: "custom-b", name: "Theme B" };

it.each([false, true])("checks queued theme ownership after remote updates (theme conflict: %s)", async conflict => {
  let server = snapshot(1, { ...DEFAULT_OWNER_PREFERENCES, customThemes: [themeA] });
  receivePreferences(server);
  let finish!: (saved: PreferencesSnapshot) => void;
  const request = vi.fn<PreferencesConnection["requestMutation"]>()
    .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
    .mockImplementation(async (_action, payload) => {
      server = snapshot(server.revision + 1, { ...server.values, ...payload.patch as object });
      return server;
    });
  const disconnect = connectPreferences({ requestMutation: request, onStatus: () => () => {}, onPreferencesUpdate: () => () => {} });
  try {
    const language = patchPreferences({ language: "zh-CN" });
    const edit = patchPreferences({ customThemes: [{ ...themeA, name: "Edited A" }] });
    server = snapshot(3, { ...server.values, language: "zh-CN", themeMode: "dark", customThemes: conflict ? [themeA, themeB] : [themeA] });
    receivePreferences(server);
    finish(snapshot(2, { ...DEFAULT_OWNER_PREFERENCES, language: "zh-CN", customThemes: [themeA] }));
    expect(await language).toBe(true);
    expect(await edit).toBe(!conflict);
    if (conflict) {
      expect(request).toHaveBeenCalledTimes(1);
      expect(readOwnerPreferences().customThemes).toEqual([themeA, themeB]);
      expect(readPreferenceStatus().error).toMatch(/changed/i);
    } else {
      expect(request).toHaveBeenLastCalledWith("preferences.update", expect.objectContaining({ expected_revision: 3 }));
      expect(readOwnerPreferences()).toMatchObject({ themeMode: "dark", customThemes: [{ ...themeA, name: "Edited A" }] });
    }
  } finally { disconnect(); }
});

it("retains serial local theme edits based on the preceding optimistic edit", async () => {
  let server = snapshot(0);
  let finish!: (saved: PreferencesSnapshot) => void;
  const request = vi.fn<PreferencesConnection["requestMutation"]>()
    .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
    .mockImplementation(async (_action, payload) => {
      server = snapshot(server.revision + 1, { ...server.values, ...payload.patch as object });
      return server;
    });
  const disconnect = connectPreferences({ requestMutation: request, onStatus: () => () => {}, onPreferencesUpdate: () => () => {} });
  try {
    const first = patchPreferences({ customThemes: [themeA] });
    const second = patchPreferences({ customThemes: [themeA, themeB] });
    server = snapshot(1, { ...server.values, customThemes: [themeA] });
    finish(server);
    expect(await first).toBe(true);
    expect(await second).toBe(true);
    expect(readOwnerPreferences().customThemes).toEqual([themeA, themeB]);
  } finally { disconnect(); }
});

it("acknowledges each enqueue when a caller reuses the same patch object", async () => {
  const patch = { codeWrap: false };
  let firstAcknowledged = false;
  void patchPreferences(patch).then(saved => { firstAcknowledged = saved; });
  const second = patchPreferences(patch);
  let revision = 0;
  const disconnect = connectPreferences({
    requestMutation: async () => snapshot(++revision, { ...DEFAULT_OWNER_PREFERENCES, codeWrap: false }),
    onStatus: () => () => {}, onPreferencesUpdate: () => () => {},
  });
  try {
    expect(await second).toBe(true);
    await Promise.resolve();
    expect(firstAcknowledged).toBe(true);
  } finally { disconnect(); }
});
