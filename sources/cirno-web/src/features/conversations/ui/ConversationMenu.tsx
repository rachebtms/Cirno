import { Dropdown } from "@heroui/react";
import { Archive, Folder, ListChecks, Pencil, Pin, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ChatSummary } from "@/lib/contracts/conversations";
import { useConversationCatalog } from "../catalog/context";
export function ConversationMenu({ session, title, onRename, onSelect }: {
  session: ChatSummary; title: string; onRename: () => void; onSelect: () => void;
}) {
  const { t } = useTranslation();
  const catalog = useConversationCatalog();
  const pinned = catalog.preferences?.pinned_keys.includes(session.key);
  const archived = catalog.preferences?.archived_keys.includes(session.key);
  return <Dropdown.Menu aria-label={t("chat.actions", { title })}>
    <Dropdown.Item id="pin" textValue={t(pinned ? "chat.unpin" : "chat.pin")} onAction={() => catalog.togglePin(session.key)}><Pin size={15} />{t(pinned ? "chat.unpin" : "chat.pin")}</Dropdown.Item>
    <Dropdown.Item id="rename" textValue={t("chat.rename")} onAction={onRename}><Pencil size={15} />{t("chat.rename")}</Dropdown.Item>
    <Dropdown.Item id="archive" textValue={t(archived ? "chat.unarchive" : "chat.archive")} onAction={() => catalog.toggleArchive(session.key)}><Archive size={15} />{t(archived ? "chat.unarchive" : "chat.archive")}</Dropdown.Item>
    <Dropdown.SubmenuTrigger><Dropdown.Item id="project" isDisabled={catalog.assigning} textValue={t("features.projects")}><Folder size={15} />{t("features.projects")}<Dropdown.SubmenuIndicator /></Dropdown.Item>
      <Dropdown.Popover><Dropdown.Menu aria-label={t("features.projects")} selectionMode="single" selectedKeys={[session.projectId ?? ":unfiled"]}
        onAction={key => catalog.assign(session.key, key === ":unfiled" ? null : String(key))}>
        {[{ id: ":unfiled", name: t("conversationCatalog.unfiled") }, ...catalog.projects].map(project =>
          <Dropdown.Item key={project.id} id={project.id} textValue={project.name}>{project.name}<Dropdown.ItemIndicator /></Dropdown.Item>)}
      </Dropdown.Menu></Dropdown.Popover>
    </Dropdown.SubmenuTrigger>
    <Dropdown.Item id="select" textValue={t("chat.select")} onAction={onSelect}><ListChecks size={15} />{t("chat.select")}</Dropdown.Item>
    <Dropdown.Item id="delete" variant="danger" textValue={t("chat.delete")} onAction={() => void catalog.deleteConversation(session.key, title)}><Trash2 size={15} />{t("chat.delete")}</Dropdown.Item>
  </Dropdown.Menu>;
}
