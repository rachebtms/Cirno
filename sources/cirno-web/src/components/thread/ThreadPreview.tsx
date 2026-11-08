import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { WorkspaceFiles } from "@/features/files/WorkspaceFiles";
import { useTranslation } from "react-i18next";

import { FileActionsProvider } from "@/components/FileActions";
import { FilePreviewPanel } from "@/components/FilePreviewPanel";
import { PreviewPane } from "@/components/PreviewPane";

import type { useThreadPreview } from "./useThreadPreview";

export function ThreadPreview({ controller }: { controller: ReturnType<typeof useThreadPreview> }) {
  const { t } = useTranslation();
  const {
    activePreview, previewStoreKey, visiblePreview, filePreviewWidth, filePreviewClosing, guardPreview,
    selectTab, handleClosePreviewTab, handleCloseFilePreview, handleFilePreviewResizeStart,
    workspaceScope, client, previewSessionKey, setBrowserDirty, token, filePreviews, resolveFile,
    pendingPreviewAction, setPendingPreviewAction, fileActions, openFilePreview,
  } = controller;
  return <>
    {activePreview ? (
      <FileActionsProvider key={previewStoreKey} value={fileActions}>
        <PreviewPane
          key={previewStoreKey}
          tabs={visiblePreview.tabs}
          activeId={activePreview.id}
          width={filePreviewWidth}
          isClosing={filePreviewClosing}
          onSelect={id => guardPreview(() => selectTab(id))}
          onCloseTab={id => guardPreview(() => handleClosePreviewTab(id))}
          onClose={() => guardPreview(handleCloseFilePreview)}
          onResizeStart={handleFilePreviewResizeStart}
        >
          {activePreview.kind === "browser" ? <WorkspaceFiles key={`${previewStoreKey}:${workspaceScope?.project_path ?? "default"}`} client={client} sessionKey={previewSessionKey} workspaceScope={workspaceScope} onDirtyChange={setBrowserDirty} /> : previewSessionKey ? <FilePreviewPanel
            key={activePreview.id}
            sessionKey={previewSessionKey}
            path={activePreview.value}
            token={token}
            loadPreview={filePreviews.load}
            initialPreview={filePreviews.peek(activePreview.value)}
            onOpenFilePreview={openFilePreview}
            onResolvePath={resolveFile}
          /> : null}
        </PreviewPane>
      </FileActionsProvider>
    ) : null}
    <AlertDialog open={pendingPreviewAction !== null} onOpenChange={open => { if (!open) setPendingPreviewAction(null); }}>
      <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{t("files.discardTitle")}</AlertDialogTitle><AlertDialogDescription>{t("files.discardDescription")}</AlertDialogDescription></AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel>{t("files.cancel")}</AlertDialogCancel><AlertDialogAction onClick={() => { setBrowserDirty(false); pendingPreviewAction?.(); setPendingPreviewAction(null); }}>{t("files.discard")}</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </>;
}
