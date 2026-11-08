import { useState } from "react";
import { Workbench } from "@/features/workbench/Workbench";
import type { CirnoClient } from "@/lib/cirno-client";
import { ThreadShell } from "@/components/thread/ThreadShell";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { StartupSkeleton } from "@/components/StartupSkeleton";
import { settings } from "@/dev/gallery/settings";
import "@/components/startup-skeleton.css";

const noop = () => {};

export function NewChatSkeletonFixture() {
  const params = new URLSearchParams(location.search);
  const [workspaceScope, setWorkspaceScope] = useState<WorkspaceScopePayload>({ project_path: "/workspace", access_mode: "full" });
  const dark = params.has("dark");
  document.documentElement.classList.toggle("dark", dark);
  return <div className="overflow-hidden bg-background" style={{ height: "100dvh" }}>
    {params.has("loading") ? <StartupSkeleton /> : <Workbench
      client={{ requestMutation: async () => ({}) } as unknown as CirnoClient}
      route={{ view: "chat", activeKey: null, settingsSection: "overview" }} navigationSequence={0}
      title="New conversation" sessions={[]} scope={workspaceScope} onRoute={noop} onNewChat={noop}
      beforeActivate={action => action()} onRouteVisibleChange={noop}>
      <main className="thread-workspace relative flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        <ThreadShell session={null} title="Cirno" onToggleSidebar={noop} theme={dark ? "dark" : "light"}
          hideDesktopSidebarToggle onTemporaryChatEnabledChange={noop} settingsSnapshot={settings}
          workspaceScope={workspaceScope}
          workspaceDefaultScope={{ project_path: "/workspace", access_mode: "full" }}
          workspaceControls={{ can_change_project: true, can_browse_directories: true }} onWorkspaceScopeChange={setWorkspaceScope} />
      </main>
    </Workbench>}
  </div>;
}
