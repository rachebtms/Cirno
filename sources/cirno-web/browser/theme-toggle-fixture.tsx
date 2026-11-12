import { useState } from "react";
import { Workbench } from "@/features/workbench/Workbench";
import { SettingsNavigation } from "@/features/settings/ui/SettingsNavigation";
import type { SettingsSectionKey } from "@/features/settings/contracts";
import type { CirnoClient } from "@/lib/cirno-client";
import { ThreadViewport } from "@/components/thread/ThreadViewport";
import { ThreadHistoryStatus } from "@/components/thread/ThreadHistoryStatus";
import { formatQuotedUserMessage } from "@/lib/user-message-quote";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { UIMessage } from "@/lib/contracts/messages";
import { ThreadComposer } from "@/components/thread/ThreadComposer";
import { ThreadHeader } from "@/components/thread/ThreadHeader";
import { ThemeProvider, useTheme } from "@/hooks/useTheme";

export function ThemeToggleFixture() {
  const { theme, toggle } = useTheme();
  return (
    <ThemeProvider theme={theme}>
      {new URLSearchParams(location.search).has("selection") ? <SettingsSelectionFixture theme={theme} toggle={toggle} /> : new URLSearchParams(location.search).has("chat") ? <ThemeChatFixture theme={theme} toggle={toggle} /> : (
        <main data-theme-surface className="thread-workspace relative flex flex-col justify-center gap-8 bg-background px-6" style={{ height: "100vh" }}>
          <div className="absolute inset-x-0 top-0">
            <ThreadHeader title="Theme preview" hideTitle theme={theme} onToggleTheme={toggle} onToggleSidebar={() => {}} />
          </div>
          <div className="workbench-body">
            <section data-theme-surface className="workbench-pane flex flex-col gap-8 bg-background">
              <h1 data-testid="hero-greeting" data-theme-ink className="text-center text-4xl text-foreground">Where should we start?</h1>
              <ThreadComposer variant="hero" onSend={() => {}} />
            </section>
          </div>
        </main>
      )}
    </ThemeProvider>
  );
}

const sessions: ChatSummary[] = ["Theme chat", "Another chat"].map((title, index) => ({
  key: `websocket:theme-${index}`, channel: "websocket", chatId: `theme-${index}`,
  title, preview: "", createdAt: null, updatedAt: null,
}));
const messages: UIMessage[] = [
  { id: "user", role: "user", content: formatQuotedUserMessage("Keep the surface layers in sync.", "Quoted context has its own translucent fill."), createdAt: 1 },
  { id: "answer", role: "assistant", content: "An existing conversation with its own composer.", createdAt: 2 },
  { id: "session", role: "user", content: "An incoming session message.", createdAt: 3,
    sessionMessage: { message_id: "incoming", session: { id: "handle_0123456789abcdef0123456789abcdef", name: "nori" } } },
];
const noop = () => {};

function ThemeChatFixture({ theme, toggle }: { theme: "light" | "dark"; toggle: () => void }) {
  const [activeKey, setActiveKey] = useState(sessions[0].key);
  const composer = <ThreadComposer onSend={noop} />;
  return <main data-theme-surface className="bg-background" style={{ height: "100vh" }}>
    <Workbench client={{ requestMutation: async () => ({}) } as unknown as CirnoClient}
      route={{ view: "chat", activeKey, settingsSection: "overview" }} navigationSequence={0}
      title="Theme chat" sessions={sessions} scope={{ project_path: "/workspace", access_mode: "full" }}
      onRoute={route => setActiveKey(route.activeKey ?? sessions[0].key)} onNewChat={noop}
      beforeActivate={action => action()} onRouteVisibleChange={noop}>
      <div className="thread-workspace relative flex min-h-0 flex-1 flex-col bg-background">
        <ThreadHeader title="Theme chat" hideTitle theme={theme} onToggleTheme={toggle} onToggleSidebar={noop} />
        <ThreadViewport messages={messages} isStreaming={false} conversationKey={activeKey} composer={composer} />
        <ThreadHistoryStatus loading={false} error={null} exhausted onRetry={noop} />
      </div>
    </Workbench>
  </main>;
}

function SettingsSelectionFixture({ theme, toggle }: { theme: "light" | "dark"; toggle: () => void }) {
  const [activeSection, setActiveSection] = useState<SettingsSectionKey>("overview");
  return <main className="flex h-screen flex-col bg-background"><ThreadHeader title="Settings" theme={theme} onToggleTheme={toggle} onToggleSidebar={noop} />
    <div className="min-h-0 flex-1"><SettingsNavigation activeSection={activeSection} onSelectSection={setActiveSection} /></div>
  </main>;
}
