import { useTheme } from "@/hooks/useTheme";
import { useState } from "react";
import { ConversationCatalogPreview } from "@/dev/fixtures/ConversationCatalogPreview";
import type { ChatSummary } from "@/lib/contracts/conversations";

const sessions: ChatSummary[] = ["Review history", "Locate messages", "Refine message bubbles", "Check MCP connection"].map((title, index) => ({
  key: `websocket:activity-${index}`,
  chatId: `activity-${index}`,
  channel: "websocket",
  title,
  preview: "",
  createdAt: "2026-10-21T10:00:00Z",
  updatedAt: "2026-10-21T10:00:00Z",
  handle: { id: `handle_activity_${index}`, name: ["bate", "jaru", "goyo", "tami"][index] },
}));

export function CatalogActivityFixture() {
  const { toggle } = useTheme();
  const [count, setCount] = useState(new URLSearchParams(location.search).has("all") ? sessions.length : 1);
  const [visible, setVisible] = useState(true);
  const [activeKey, setActiveKey] = useState(sessions[0].key);
  return <main data-selected-conversation={activeKey} className="flex min-h-screen flex-wrap items-start gap-6 bg-background p-4 text-foreground">
    <section aria-label="Conversation catalog" className="h-[620px] w-[800px] max-w-full border border-border bg-background">
      {visible && <ConversationCatalogPreview sessions={sessions} onOpen={setActiveKey}
        activity={Object.fromEntries(sessions.map((session, index) => [session.key, index < count ? "running" : null]))} />}
    </section>
    <div className="flex flex-col gap-3">
      <button onClick={() => setCount((value) => Math.min(sessions.length, value + 1))}>Start next conversation</button>
      <button onClick={() => setCount(1)}>Reset conversations</button>
      <button onClick={() => setVisible((value) => !value)}>Toggle catalog</button>
      <button onClick={toggle}>Toggle theme</button>
    </div>
  </main>;
}
