import { Workbench } from "@/features/workbench/Workbench";
import type { WorkspacePanelProps } from "@/features/workbench/contracts";
import { createWorkspaceRegistry } from "@/features/workbench/registry";
import type { CirnoClient } from "@/lib/cirno-client";
import type { ChatSummary } from "@/lib/contracts/conversations";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { File } from "lucide-react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

const route = (key: string) => ({ view: "chat", activeKey: key, settingsSection: "overview" });
const session = (key: string): ChatSummary => ({ key, title: key, preview: "", chatId: key, channel: "websocket", createdAt: null, updatedAt: null });

describe("workspace conversation deletion", () => {
  it("removes the deleted chat tab without changing a file tab's scope or unsaved draft", async () => {
    const user = userEvent.setup();
    localStorage.clear();
    function Editor({ tab }: WorkspacePanelProps) {
      const [draft, setDraft] = useState("");
      return <><p>Document scope: {tab.sessionKey}</p><input aria-label="File draft" value={draft} onChange={event => setDraft(event.target.value)} /></>;
    }
    const panels = createWorkspaceRegistry([{ id: "files", panels: [{ kind: "file", titleKey: "Test document", Icon: File, Content: Editor, tabPolicy: "multiple", showInMenu: true }] }]);
    const onRoute = vi.fn();
    const props = { client: {} as CirnoClient, panels, route: route("websocket:a"), navigationSequence: 0, sessionsLoaded: true, title: "Deleted research", onRoute,
      onNewChat: vi.fn(), onRouteVisibleChange: vi.fn(), beforeActivate: (action: () => void) => action() };
    const { rerender } = render(<Workbench {...props} sessions={[session("websocket:a"), session("websocket:b")]}><p>Chat body</p></Workbench>);
    await user.click(screen.getByRole("button", { name: "Open Test document" }));
    await user.type(screen.getByRole("textbox", { name: "File draft" }), "Keep this edit");
    rerender(<Workbench {...props} sessions={[session("websocket:b")]}><p>Chat body</p></Workbench>);
    await waitFor(() => expect(screen.queryByRole("tab", { name: "Deleted research" })).not.toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "Test document" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("textbox", { name: "File draft" })).toHaveValue("Keep this edit");
    expect(screen.getByText("Document scope: websocket:a")).toBeVisible();
    expect(onRoute).not.toHaveBeenCalled();
  });

  it("activates another existing conversation when the visible chat is deleted externally", async () => {
    localStorage.setItem("cirno-webui.workspace-tabs.v1", JSON.stringify([
      { id: "chat:websocket:b", type: "route", route: route("websocket:b") },
    ]));
    const onRoute = vi.fn();
    const props = { client: {} as CirnoClient, route: route("websocket:a"), navigationSequence: 0, sessionsLoaded: true, title: "Current research", onRoute,
      onNewChat: vi.fn(), onRouteVisibleChange: vi.fn(), beforeActivate: (action: () => void) => action() };
    const { rerender } = render(<Workbench {...props} sessions={[session("websocket:a"), session("websocket:b")]}><p>Chat body</p></Workbench>);
    rerender(<Workbench {...props} sessions={[session("websocket:b")]}><p>Chat body</p></Workbench>);
    await waitFor(() => expect(onRoute).toHaveBeenCalledWith(route("websocket:b")));
    expect(screen.queryByRole("tab", { name: "Current research" })).not.toBeInTheDocument();
  });
});
