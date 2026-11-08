import { Button, Card, Dropdown } from "@heroui/react";
import { Folder, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ProjectSummary } from "@/lib/contracts/conversations";
import { useConversationCatalog } from "../catalog/context";
import { useActiveMenu } from "@/ui/overlays/useActiveMenu";

export function ProjectSection({ project, children, onEdit, onDelete, active }: {
  project: ProjectSummary; children: ReactNode; onEdit: () => void; onDelete: () => void; active: boolean;
}) {
  const { t } = useTranslation(), headingId = useId();
  const catalog = useConversationCatalog();
  const menu = useActiveMenu(active, catalog.owner);
  return <Card className="conversation-project" role="region" aria-labelledby={headingId}>
    <Card.Header className="conversation-project-header">
      <Folder size={19} />
      <div className="conversation-project-heading"><h2 id={headingId}>{project.name}</h2>
        {project.working_directory && <p>{project.working_directory}</p>}
      </div>
      <Button isIconOnly size="sm" variant="ghost" aria-label={t("conversationCatalog.newInProject", { name: project.name })} onPress={() => catalog.create(project)}><Plus size={17} /></Button>
      <Dropdown {...menu}><Button isIconOnly size="sm" variant="ghost" aria-label={t("conversationCatalog.projectActions", { name: project.name })}><MoreHorizontal size={18} /></Button>
        <Dropdown.Popover placement="bottom end"><Dropdown.Menu aria-label={project.name}>
          <Dropdown.Item id="rename" textValue={t("conversationCatalog.renameProject", { name: project.name })} onAction={onEdit}><Pencil size={15} />{t("chat.rename")}</Dropdown.Item>
          <Dropdown.Item id="delete" variant="danger" textValue={t("conversationCatalog.deleteProject", { name: project.name })} onAction={onDelete}><Trash2 size={15} />{t("chat.delete")}</Dropdown.Item>
        </Dropdown.Menu></Dropdown.Popover>
      </Dropdown>
    </Card.Header>
    <Card.Content className="conversation-project-content">{children}</Card.Content>
  </Card>;
}
