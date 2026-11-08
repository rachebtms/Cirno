import { Button } from "@heroui/react";
import { ArrowLeft, Eye, RefreshCw, Save, SquarePen } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { DocumentViewModel, DocumentViewProps } from "../model/useDocumentView";

export function DocumentToolbar({ model, options }: { model: DocumentViewModel; options: DocumentViewProps }) {
  const { t } = useTranslation();
  const { state } = model;
  const busy = state.loading || state.saving;
  return <header className="file-document-toolbar">
    {options.onBack && <Button isIconOnly variant="ghost" isDisabled={state.saving} aria-label={t("files.back")} onPress={() => model.guard(options.onBack!)}><ArrowLeft size={18} /></Button>}
    <span className="file-document-title" title={state.file?.path ?? options.path}>{state.file?.display_path ?? options.path}{model.dirty ? " *" : ""}</span>
    <Button isIconOnly variant="ghost" isDisabled={busy} aria-label={t("files.reloadFile")} onPress={() => model.guard(() => void model.document.load())}><RefreshCw size={17} /></Button>
    {options.onOpenPreview && state.file?.kind === "text" && <Button isIconOnly variant="ghost" aria-label={t("files.openPreview")} onPress={options.onOpenPreview}><Eye size={18} /></Button>}
    {state.file?.editable && !options.preview ? <>
      <Button variant="secondary" isDisabled={busy} onPress={() => model.setEditing(!model.editing)}><SquarePen size={16} />{t(`files.${model.editing ? "preview" : "edit"}`)}</Button>
      <Button isDisabled={!model.dirty || state.loading} isPending={state.saving} onPress={() => void model.document.save()}><Save size={16} />{t("files.save")}</Button>
    </> : state.file && <span className="file-document-status">{t("files.readOnly")}</span>}
  </header>;
}
