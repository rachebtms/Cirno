import { useState } from "react";
import { useTranslation } from "react-i18next";
import { InlineMessageEditor } from "@/features/messages/InlineMessageEditor";
import { ThreadMessages } from "@/components/thread/ThreadMessages";
import type { UIMessage } from "@/lib/contracts/messages";

export function MessageActionsFixture() {
  const { i18n } = useTranslation();
  const zh = i18n.language.startsWith("zh");
  const [action, setAction] = useState("");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const now = Date.UTC(2026, 10, 3, 12, 35);
  const messages: UIMessage[] = [
    { id: "u", role: "user", content: zh ? "深入检查前后端，修复发现的问题。" : "Review the frontend and backend, then fix the bugs.", createdAt: now, turnId: "review" },
    { id: "r", role: "assistant", content: "", reasoning: zh ? "检查备份校验、会话状态与权限撤销。" : "Checking backup validation, conversation state and access revocation.", createdAt: now + 1000, turnId: "review" },
    { id: "t", role: "tool", kind: "trace", content: "", traces: ["read_file(path=\"backup/archive.py\")"], createdAt: now + 2000, turnId: "review" },
    { id: "a", role: "assistant", content: zh ? "已修复发现的问题，并验证了备份恢复和会话切换。\n\n消息操作和时间始终显示，活动详情可以直接展开。" : "The bugs are fixed. Backup recovery and conversation switching have been verified.\n\nMessage actions and timestamps stay visible; activity details open directly.", createdAt: now + 3000, completedAt: now + 53000, latencyMs: 53000, turnId: "review" },
  ];
  return <main className="mx-auto min-h-screen max-w-3xl py-10">
    <ThreadMessages messages={saved === null ? messages : [{ ...messages[0], content: saved }]}
      onEditMessage={message => { setDraft(message.content); setEditing(true); setAction("edit"); }}
      onForkFromMessage={() => setAction("fork")}
      messageEditor={editing ? { messageId: "u", content: <InlineMessageEditor
        value={draft} busy={false} error="" hasToolEffects onChange={setDraft}
        onCancel={() => setEditing(false)} onSubmit={() => { setSaved(draft); setEditing(false); }} /> } : undefined} />
    <output aria-label="Fixture action" className="sr-only">{action}</output>
  </main>;
}
