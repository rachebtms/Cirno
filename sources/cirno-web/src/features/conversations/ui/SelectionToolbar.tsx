import { Alert, Button } from "@heroui/react";
import { Archive, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/ui/feedback/ConfirmDialog";
import { useConversationCatalog } from "../catalog/context";
import type { ConversationSelection } from "../shared/useConversationSelection";
export function SelectionToolbar({ selection }: { selection: ConversationSelection }) {
  const { t } = useTranslation();
  const catalog = useConversationCatalog();
  const { pendingArchive } = selection;
  return <>
    {selection.deleteSelectionMode && <div className="conversation-selection-toolbar" ref={selection.selectionBarRef} data-testid="delete-selection-bar" aria-busy={selection.deleteConfirmationPending}>
      <span>{t("chat.selectedCount", { count: selection.selectedDeleteKeys.size })}</span>
      <Button variant="secondary" size="sm" isDisabled={!selection.selectedDeleteKeys.size || selection.selectionConfirmationPending}
        onPress={() => selection.setPendingArchive({ keys: [...selection.selectedDeleteKeys], archive: !selection.allSelectedArchived })}>
        <Archive size={15} />{t(selection.allSelectedArchived ? "chat.unarchive" : "chat.archive")}</Button>
      <Button variant="danger-soft" size="sm" isDisabled={!selection.selectedDeleteKeys.size || selection.selectionConfirmationPending} onPress={selection.confirmDeleteSelection}><Trash2 size={15} />{t("chat.delete")}</Button>
      <Button variant="ghost" size="sm" isDisabled={selection.selectionConfirmationPending} onPress={selection.closeDeleteSelection}>{t("common.cancel")}</Button>
    </div>}
    {selection.selectionError && <Alert status="danger" role="alert"><Alert.Description>{selection.selectionError}</Alert.Description></Alert>}
    {pendingArchive && <ConfirmDialog title={t(pendingArchive.archive ? "archiveConfirm.titleMany" : "archiveConfirm.unarchiveTitleMany", { count: pendingArchive.keys.length })}
      description={t(pendingArchive.archive ? "archiveConfirm.description" : "archiveConfirm.unarchiveDescription")}
      action={t(pendingArchive.archive ? "chat.archive" : "chat.unarchive")} onClose={() => selection.setPendingArchive(null)}
      onConfirm={() => { catalog.archiveMany(pendingArchive.keys, pendingArchive.archive); selection.closeDeleteSelection(); }} />}
  </>;
}
