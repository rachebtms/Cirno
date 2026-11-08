import { beforeEach, expect, it, vi } from "vitest";
import { migrateBrowserCirnoIdentity } from "@/lib/migrate-cirno-identity";
beforeEach(() => localStorage.clear());
it("migrates tab groups and draft targets without changing written text", () => {
  const old = "websocket:global", next = "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb";
  localStorage.setItem("cirno-webui.workspace-tabs.v1", JSON.stringify([{ id: `chat:${old}`, type: "route", group: 1, route: { view: "chat", activeKey: old, settingsSection: "overview" } }]));
  localStorage.setItem("cirno-webui.tab-groups.v1", JSON.stringify({ selected: [null, `chat:${old}`] }));
  const key = `cirno.composer-draft.v1.${old}`;
  localStorage.setItem(key, JSON.stringify({ text: `literal ${old}`, targets: [{ id: "handle_335e48447b25d7e301b326b3db91c36c", name: "cirno" }] }));
  const replace = vi.spyOn(history, "replaceState");
  migrateBrowserCirnoIdentity(localStorage, { hash: `#/chat/${encodeURIComponent(old)}` } as Location);
  expect(JSON.parse(localStorage.getItem("cirno-webui.workspace-tabs.v1")!)[0]).toMatchObject({ id: `chat:${next}`, group: 1, route: { activeKey: next } });
  expect(JSON.parse(localStorage.getItem("cirno-webui.tab-groups.v1")!).selected).toEqual([null, `chat:${next}`]);
  expect(localStorage.getItem(key)).toBeNull();
  expect(JSON.parse(localStorage.getItem(`cirno.composer-draft.v1.${next}`)!)).toMatchObject({ text: `literal ${old}`, targets: [{ id: "handle_9daf584999d74888c635d1df82976250", name: "cirno" }] });
  expect(replace).toHaveBeenCalledWith(null, "", `#/chat/${encodeURIComponent(next)}`);
  replace.mockRestore();
});
it("keeps malformed old data and reports its migration failure while updating other tabs", () => {
  const key = "cirno.composer-draft.v1.websocket:global";
  localStorage.setItem(key, 'broken websocket:global');
  localStorage.setItem("cirno-webui.workspace-tabs.v1", JSON.stringify([{ id: "chat:websocket:global", route: { activeKey: "websocket:global" } }]));
  const errors = migrateBrowserCirnoIdentity(localStorage, { hash: "#/new" } as Location);
  expect(errors).toHaveLength(1);
  expect(errors[0]).toContain(key);
  expect(localStorage.getItem(key)).toBe('broken websocket:global');
  expect(localStorage.getItem("cirno-webui.workspace-tabs.v1")).toContain("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb");
});
