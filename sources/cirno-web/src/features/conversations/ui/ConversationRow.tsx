import { Button, Dropdown } from "@heroui/react";
import { Archive, Check, MessageCircle, MoreHorizontal, Pin } from "lucide-react";
import { useId, useState } from "react";
import { useActiveMenu } from "@/ui/overlays/useActiveMenu";
import { useTranslation } from "react-i18next";
import { displayTitle } from "@/lib/chat-groups";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { ConversationSelection } from "../shared/useConversationSelection";
import { useConversationCatalog } from "../catalog/context";
import { ConversationMenu } from "./ConversationMenu";
import { RenameDialog } from "./RenameDialog";
import { ConversationStatus } from "./ConversationStatus";
export function ConversationRow({ session, selection, active }: { session: ChatSummary; selection: ConversationSelection; active: boolean }) {
  const { t } = useTranslation();
  const catalog = useConversationCatalog();
  const menu = useActiveMenu(active, catalog.owner);
  const [renameOwner, setRenaming] = useState<object | null>(null);
  const renaming = renameOwner === catalog.owner;
  const title = displayTitle(session, catalog.preferences?.title_overrides ?? {}, t("sidebar.newChat"));
  const activity = catalog.activity?.[session.key];
  const activityId = useId();
  return <div className="conversation-row" data-chat-row={session.key} onContextMenu={event => {
    if (!selection.deleteSelectionMode) { event.preventDefault(); menu.onOpenChange(true); }
  }}>
    <Button variant="ghost" className="conversation-open" aria-label={title} aria-describedby={activity ? activityId : undefined}
      aria-pressed={selection.deleteSelectionMode ? selection.selectedDeleteKeys.has(session.key) : undefined}
      isDisabled={selection.selectionConfirmationPending}
      onPress={event => selection.deleteSelectionMode ? selection.toggleDeleteSelection([session.key], event.shiftKey) : catalog.open(session.key)}>
      {selection.deleteSelectionMode ? <span className="conversation-selection" data-checked={selection.selectedDeleteKeys.has(session.key)}><Check size={14} /></span> : <MessageCircle size={18} />}
      <span className="conversation-description"><span className="conversation-title">{title}
        {catalog.preferences?.pinned_keys.includes(session.key) && <Pin size={12} />}
        {catalog.preferences?.archived_keys.includes(session.key) && <Archive size={12} />}
        {activity && <ConversationStatus state={activity} id={activityId} />}
      </span><span className="conversation-preview">{session.handle && <span className="conversation-handle">@{session.handle.name}</span>}{session.preview}</span></span>
    </Button>
    {!selection.deleteSelectionMode && <Dropdown {...menu}>
      <Button isIconOnly variant="ghost" className="conversation-actions" aria-label={t("chat.actions", { title })}><MoreHorizontal size={18} /></Button>
      <Dropdown.Popover placement="bottom end"><ConversationMenu session={session} title={title} onRename={() => setRenaming(catalog.owner)} onSelect={() => selection.beginDeleteSelection([session.key])} /></Dropdown.Popover>
    </Dropdown>}
    {renaming && <RenameDialog sessionKey={session.key} title={title} open={active} onClose={() => setRenaming(null)} />}
  </div>;
}
