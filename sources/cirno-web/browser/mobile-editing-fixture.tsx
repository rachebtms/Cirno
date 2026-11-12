import { useEffect, useState } from "react";
import { ThreadShell } from "@/components/thread/ThreadShell";
import { settings } from "@/dev/gallery/settings";
import { useAppViewport } from "@/hooks/useAppViewport";
import { useTheme } from "@/hooks/useTheme";
import { CirnoClient } from "@/lib/cirno-client";
import type { ChatSummary } from "@/lib/contracts/conversations";
import { ClientProvider } from "@/providers/ClientProvider";
import { Workbench } from "@/features/workbench/Workbench";
import type { WorkspaceRoute } from "@/features/workbench/contracts";

const session: ChatSummary = {
  key: "websocket:mobile-edit", chatId: "mobile-edit", channel: "websocket",
  createdAt: null, updatedAt: null, preview: "", title: "Mobile editing",
};
const sessions = [session];

/** Shipping shell, transcript, editor and composer with a controlled backend. */
export function MobileEditingFixture() {
  useTheme();
  useAppViewport();
  const [client] = useState(() => new CirnoClient({
    url: `ws://${location.host}/mobile-edit-fixture-ws`, reconnect: false,
  }));
  const [route, setRoute] = useState<WorkspaceRoute>({
    view: "chat", activeKey: session.key, settingsSection: "overview",
  });
  useEffect(() => { client.connect(); return () => client.close(); }, [client]);
  return <ClientProvider client={client} token="mobile-edit-fixture" webuiCapabilities={["webui.prompt-navigation.v1"]}>
    <Workbench client={client} route={route} onRoute={setRoute} navigationSequence={0}
      sessions={sessions} sessionsLoaded title="Mobile editing"
      onRouteVisibleChange={() => {}} onNewChat={() => {}} beforeActivate={action => action()}
      renderRoute={(_route, visible, focused) => <ThreadShell session={session} sessions={sessions}
        title="Mobile editing" onToggleSidebar={() => {}} settingsSnapshot={settings}
        composerActive={visible} headerActive={focused} />} />
  </ClientProvider>;
}
