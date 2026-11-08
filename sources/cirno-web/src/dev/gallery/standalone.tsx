import { useState } from "react";

import { ConversationCatalogPreview } from "../fixtures/ConversationCatalogPreview";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { ConnectionStatus } from "@/lib/contracts/transport";
import { StatePicker, type ComponentExample } from "./example";
import { useGalleryTranslation } from "./i18n";

function ConnectionPreview() {
  const { t } = useGalleryTranslation();
  const [status, setStatus] = useState<ConnectionStatus>("open");
  return <><StatePicker label={t("previews.connectionBadge.state")} value={status} options={["idle", "connecting", "open", "reconnecting", "closed", "error"]} onChange={setStatus} />
    <div className="flex items-center gap-3"><ConnectionBadge status={status} /><span className="text-sm">{t(`previews.connectionBadge.${status}`)}</span></div></>;
}


const initialSessions: ChatSummary[] = [
  { key: "websocket:gallery-components", chatId: "gallery-components", channel: "websocket", title: "组件设计", preview: "模型选择、消息输入和设置表单。",
    createdAt: "2026-10-01T12:00:00Z", updatedAt: "2026-10-13T08:00:00Z", handle: { id: "gallery-components", name: "design" } },
  { key: "websocket:gallery-tests", chatId: "gallery-tests", channel: "websocket", title: "验证交互", preview: "检查错误状态与键盘操作。",
    createdAt: "2026-10-02T12:00:00Z", updatedAt: "2026-10-13T09:00:00Z", handle: { id: "gallery-tests", name: "tests" } },
  { key: "websocket:gallery-history", chatId: "gallery-history", channel: "websocket", title: "历史方案", preview: "已归档的会话示例。",
    createdAt: "2026-10-01T10:00:00Z", updatedAt: "2026-10-05T10:00:00Z", handle: { id: "gallery-history", name: "history" } },
];

function ChatsPreview() {
  const { t } = useGalleryTranslation();
  const [active, setActive] = useState<string | null>(initialSessions[0].key);
  const [mode, setMode] = useState<"ready" | "loading" | "empty">("ready");
  const [renamed, setRenamed] = useState<string | null>(null);
  return <><StatePicker label={t("previews.chats.state")} value={mode} options={["ready", "loading", "empty"]} onChange={setMode} />
    <div className="h-[28rem] overflow-hidden rounded-panel border border-border bg-background">
      <ConversationCatalogPreview key={mode} sessions={mode === "ready" ? initialSessions : []} loading={mode === "loading"} onOpen={setActive} onRename={setRenamed} />
    </div>
    <p role="status" className="mt-4 text-sm text-muted-foreground">{renamed !== null ? t("previews.chats.renamed", { name: renamed })
      : t("previews.chats.selected", { name: active ?? t("previews.chats.none") })}</p></>;
}



const components = "sources/cirno-web/src/components/";
export const standaloneExamples: ComponentExample[] = [
  { title: "previews.connectionBadge.title", files: [`${components}ConnectionBadge.tsx`], Preview: ConnectionPreview,
    description: "previews.connectionBadge.description", options: "previews.connectionBadge.options",
    code: '<ConnectionBadge status={status} />' },
  { title: "previews.chats.title", files: ["sources/cirno-web/src/features/conversations/catalog/ConversationsPage.tsx"], Preview: ChatsPreview,
    description: "previews.chats.description", options: "previews.chats.options",
    code: '<ConversationCatalogPreview sessions={sessions} />' },
  { title: "previews.language.title", files: [`${components}LanguageSwitcher.tsx`], Preview: LanguageSwitcher,
    description: "previews.language.description", options: "previews.language.options",
    code: '<LanguageSwitcher />' },
];
