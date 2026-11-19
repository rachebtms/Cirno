import { beforeEach, expect, it } from "vitest";
import { filesModule } from "@/features/files/module";
import { createWorkspaceRegistry } from "@/features/workbench/registry";
import { restoreTabs } from "@/features/workbench/model/persistence";

const panels = createWorkspaceRegistry([filesModule]);
const route = { view: "chat", activeKey: null, settingsSection: "overview" };
beforeEach(() => localStorage.clear());
for (const [name, fields] of [
  ["non-string file path", { path: 42 }],
  ["non-object workspace scope", { scope: "/research" }],
  ["invalid workspace permissions", { scope: { project_path: "/research", access_mode: "unknown" } }],
] as const) {
  it(`recovers from a persisted ${name} before mounting feature views`, () => {
    localStorage.setItem("cirno-webui.workspace-tabs.v1", JSON.stringify([
      { id: "document", type: "file", sessionKey: null, ...fields },
    ]));
    const result = restoreTabs(route, panels);
    expect(result.error).toContain("invalid format");
    expect(result.tabs).toHaveLength(1);
    expect(result.tabs[0]).toMatchObject({ type: "route", route });
  });
}
it("rejects duplicate mounted IDs across distinct panel policies", () => {
  localStorage.setItem("cirno-webui.workspace-tabs.v1", JSON.stringify([
    { id: "same-id", type: "files", sessionKey: null },
    { id: "same-id", type: "file", path: "notes.md", sessionKey: null },
  ]));
  const result = restoreTabs(route, panels);
  expect(result.error).toContain("invalid format");
  expect(result.tabs).toHaveLength(1);
});
it("also detects collisions with the current route added during restoration", () => {
  localStorage.setItem("cirno-webui.workspace-tabs.v1", JSON.stringify([
    { id: "chat:new", type: "file", path: "notes.md", sessionKey: null },
  ]));
  const result = restoreTabs(route, panels);
  expect(result.error).toContain("invalid format");
  expect(result.tabs).toHaveLength(1);
  expect(result.tabs[0]).toMatchObject({ type: "route", route });
});
it("retains separate conversation documents and their split groups on restoration", () => {
  localStorage.setItem("cirno-webui.workspace-tabs.v1", JSON.stringify([
    { id: "a", type: "file", path: "notes.md", sessionKey: "websocket:a", group: 0,
      scope: { project_path: "/research", access_mode: "full" } },
    { id: "b", type: "file", path: "notes.md", sessionKey: "websocket:b", group: 1,
      scope: { project_path: "/research", access_mode: "review" } },
  ]));
  const result = restoreTabs(route, panels);
  expect(result.error).toBe("");
  expect(result.tabs.filter(tab => tab.type === "file")).toMatchObject([
    { id: "a", sessionKey: "websocket:a", group: 0 },
    { id: "b", sessionKey: "websocket:b", group: 1 },
  ]);
});
