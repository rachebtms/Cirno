import { Alert, Spinner, TextArea } from "@heroui/react";
import { useTranslation } from "react-i18next";
import { FilePreviewPanelView } from "@/components/FilePreviewPanelView";
import { useDocumentView, type DocumentViewProps } from "./model/useDocumentView";
import { DocumentToolbar } from "./ui/DocumentToolbar";
import { DiscardDocumentDialog } from "./ui/DiscardDocumentDialog";
import "./files.css";

export function FileDocumentView(props: DocumentViewProps) {
  const { t } = useTranslation();
  const model = useDocumentView(props);
  const { state } = model;
  return <section className="file-document" aria-label={state.file?.display_path ?? props.path} aria-busy={state.loading}>
    <DocumentToolbar model={model} options={props} />
    {(state.error || model.mediaError) && <Alert status="danger" role="alert"><Alert.Description>{state.error || model.mediaError}</Alert.Description></Alert>}
    {state.file?.editable && model.editing && !props.preview ? <TextArea
      aria-label={t("files.contents")} value={state.draft} disabled={state.loading || state.saving} spellCheck={false} wrap="off"
      className="file-document-editor" onChange={event => model.document.edit(event.target.value)}
      onKeyDown={event => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") { event.preventDefault(); void model.document.save(); } }}
    /> : model.payload && (props.active ?? true) ? <div className="file-document-preview"><FilePreviewPanelView
      path={state.file?.path ?? props.path} state={{ status: "ready", payload: model.payload }}
      imageOpen={model.imageOpen} onImageOpenChange={model.setImageOpen} onImageError={() => model.setMediaError(t("files.imageError"))}
      onOpenFilePreview={props.onReplaceFile ? path => model.guard(() => props.onReplaceFile!(path)) : props.onOpenFile}
    /></div> : !state.error && !state.file && <div role="status" className="files-loading"><Spinner size="sm" /><span>{t("workspace.loading")}</span></div>}
    <DiscardDocumentDialog model={model} />
  </section>;
}
