import { useMemo } from "react";
import { InboxPage } from "@/features/inbox/InboxPage";
import { Workbench } from "@/features/workbench/Workbench";
import { InboxProvider, type InboxCategory, type InboxNotice } from "@/features/inbox/model/store";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";
import { useTheme } from "@/hooks/useTheme";

export function InboxFixture() {
  useTheme();
  const client = useMemo(() => {
    let items: InboxNotice[] = [
      { category: "operations", kind: "question", body: "Which experiment should run next?" },
      { category: "conversations", kind: "report", body: "The paper review is ready.", data: { session_title: "Research review" } },
      { category: "system", kind: "turn", body: "Configure a model before sending your message." },
      { category: "system", kind: "compaction", body: "Conversation checkpoint saved." },
    ].map((item, index) => ({ ...item, id: String(index + 1), seq: index + 1, category: item.category as InboxCategory,
      session_key: "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", status: "pending", data: item.data ?? {}, created_at: 1793948400000, read_at: null }));
    return { status: "open", onStatus: () => () => {}, requestMutation: async (_method: string, args: { action: string; values: { category?: string } }) => {
      if (args.action === "inbox.read") items = items.map(item => ({ ...item, read_at: Date.now() }));
      return { items: items.filter(item => !args.values?.category || item.category === args.values.category), unread: { operations: 1, conversations: 1, system: 2 }, latest_seq: 4, next_before: null };
    } } as unknown as CirnoClient;
  }, []);
  return <ClientProvider client={client} token="fixture"><InboxProvider>
    <div className="h-dvh w-full overflow-hidden">
      <Workbench client={client} route={{ view: "inbox", activeKey: null, settingsSection: "overview" }}
        navigationSequence={0} title="Inbox" sessions={[]} inboxUnread={4}
        onRoute={() => {}} onNewChat={() => {}} beforeActivate={action => action()} onRouteVisibleChange={() => {}}>
        <InboxPage onBack={() => {}} onSelect={() => {}} onSettings={() => {}} />
      </Workbench>
    </div>
  </InboxProvider></ClientProvider>;
}
