import { Alert, Button } from "@heroui/react";
import { FolderPlus, Plus } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Page, PageHeader } from "@/ui/layout/Page";
import { ConfirmDialog } from "@/ui/feedback/ConfirmDialog";
import type { ProjectSummary } from "@/lib/contracts/conversations";
import { useConversationCatalog } from "./catalog/context";
import { projectConversationCatalog } from "./catalog/projection";
import { useCatalogSelection } from "./catalog/useCatalogSelection";
import { CatalogToolbar } from "./ui/CatalogToolbar";
import { ConversationList } from "./ui/ConversationList";
import { ProjectSection } from "./ui/ProjectSection";
import { ProjectDialog } from "./ui/ProjectDialog";
import { SelectionToolbar } from "./ui/SelectionToolbar";
import "./conversations.css";
export function ConversationsPage({ active = true }: { active?: boolean }) {
  const { t } = useTranslation();
  const catalog = useConversationCatalog();
  const [query, setQuery] = useState("");
  const [editor, setEditor] = useState<{ owner: object; project: ProjectSummary | null } | null>(null);
  const [deleteRequest, setDeleting] = useState<{ owner: object; project: ProjectSummary } | null>(null);
  const editing = editor?.owner === catalog.owner ? editor : null;
  const deleting = deleteRequest?.owner === catalog.owner ? deleteRequest.project : null;
  const viewport = useRef<HTMLElement>(null);
  const projection = useMemo(() => projectConversationCatalog(catalog, query), [catalog, query]);
  const rows = useMemo(() => [...projection.groups.flatMap(group => group.members), ...projection.unfiled], [projection]);
  const selection = useCatalogSelection(rows, viewport);
  const errors = [...new Set([catalog.error, catalog.preferencesError, catalog.projectError].filter(Boolean))];
  const { closeDeleteSelection } = selection;
  useEffect(() => { if (!active) closeDeleteSelection(); }, [active, closeDeleteSelection]);
  return <Page ref={viewport} label={t("workspace.library")} className="conversation-catalog" busy={catalog.loading}>
    <PageHeader title={t("workspace.library")} actions={<>
      <Button variant="secondary" size="sm" onPress={() => setEditor({ owner: catalog.owner, project: null })}><FolderPlus size={16} />{t("conversationCatalog.newProject")}</Button>
      <Button size="sm" onPress={() => catalog.create()}><Plus size={17} />{t("sidebar.newChat")}</Button>
    </>} />
    <CatalogToolbar query={query} onChange={setQuery} active={active} />
    {errors.length > 0 && <Alert role="alert" status="danger"><Alert.Content>{errors.map(error => <Alert.Description key={error}>{error}</Alert.Description>)}</Alert.Content>
      {catalog.preferencesError && catalog.retryPreferences && <Button variant="secondary" isDisabled={catalog.loading} onPress={catalog.retryPreferences}>{t("common.retry")}</Button>}
      {catalog.projectError && catalog.retryProjects && <Button variant="secondary" isDisabled={catalog.loading} onPress={catalog.retryProjects}>{t("common.retry")}</Button>}</Alert>}
    <div className="conversation-projects">{projection.groups.map(({ project, members }) => <ProjectSection key={project.id} project={project} active={active}
      onEdit={() => setEditor({ owner: catalog.owner, project })} onDelete={() => setDeleting({ owner: catalog.owner, project })}>
      {members.length ? <ConversationList rows={members} selection={selection} active={active} /> : <p className="conversation-empty">{t("conversationCatalog.emptyProject")}</p>}
    </ProjectSection>)}</div>
    <section className="conversation-unfiled"><h2>{t("conversationCatalog.unfiled")}</h2>
      {projection.unfiled.length ? <ConversationList rows={projection.unfiled} selection={selection} active={active} /> : <p className="conversation-empty" role={catalog.loading ? "status" : undefined}>{t(catalog.loading ? "workspace.loading" : "conversationCatalog.empty")}</p>}
    </section>
    <SelectionToolbar selection={selection} />
    {editing && <ProjectDialog key={editing.project?.id ?? ":new"} project={editing.project} open={active} onClose={() => setEditor(null)} />}
    {deleting && <ConfirmDialog key={deleting.id} owner={catalog.owner} open={active} title={t("conversationCatalog.deleteProject", { name: deleting.name })} description={t("conversationCatalog.deleteHelp")}
      danger action={t("workspace.delete")} onConfirm={() => catalog.deleteProject(deleting.id)} onClose={() => setDeleting(null)} />}
  </Page>;
}
