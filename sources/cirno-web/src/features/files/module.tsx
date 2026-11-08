import type {
  WorkspaceModule,
  WorkspacePanelProps,
} from "@/features/workbench/contracts";
import { Eye, File, FolderOpen } from "lucide-react";
import { lazy, useCallback } from "react";
import { FileDocumentsProvider } from "./documents";
import { useWorkspaceOpen } from "@/features/workbench/context";

const WorkspaceFiles = lazy(() =>
  import("./WorkspaceFiles").then((module) => ({
    default: module.WorkspaceFiles,
  })),
);
const FileDocumentView = lazy(() =>
  import("./FileDocumentView").then((module) => ({
    default: module.FileDocumentView,
  })),
);
function FilePanel({
  tab,
  client,
  openFile,
  setDirty,
  active,
  registerClose,
}: WorkspacePanelProps) {
  const open = useWorkspaceOpen();
  const dirty = useCallback(
    (value: boolean) => setDirty(tab.id, value),
    [setDirty, tab.id],
  );
  const register = useCallback((close: () => Promise<void>) => registerClose(tab.id, close), [registerClose, tab.id]);
  if (tab.type !== "files")
    return (
      <FileDocumentView
        client={client}
        path={tab.path ?? ""}
        sessionKey={tab.sessionKey}
        scope={tab.scope}
        active={active}
        preview={tab.type === "files.preview"}
        onDirtyChange={dirty}
        onRegisterClose={register}
        onOpenFile={(path) => openFile(path, tab)}
        onOpenPreview={
          tab.type === "file"
            ? () =>
                open?.("files.preview", {
                  path: tab.path,
                  sessionKey: tab.sessionKey,
                  scope: tab.scope,
                })
            : undefined
        }
      />
    );
  return (
    <WorkspaceFiles
      client={client}
      sessionKey={tab.sessionKey}
      workspaceScope={tab.scope}
      onOpenFile={(path) => openFile(path, tab)}
    />
  );
}
export const filesModule: WorkspaceModule = {
  id: "files",
  Provider: FileDocumentsProvider,
  panels: [
    {
      kind: "files",
      titleKey: "workspace.files",
      Icon: FolderOpen,
      Content: FilePanel,
      tabPolicy: "multiple",
      showInMenu: true,
    },
    {
      kind: "file",
      titleKey: "workspace.file",
      Icon: File,
      Content: FilePanel,
      tabPolicy: { identity: tab => JSON.stringify([tab.scope?.project_path, tab.path]) },
      showInMenu: false,
      title: (tab) => tab.path?.split("/").pop(),
    },
    {
      kind: "files.preview",
      titleKey: "filePreview.preview",
      Icon: Eye,
      Content: FilePanel,
      tabPolicy: { identity: tab => JSON.stringify([tab.scope?.project_path, tab.path]) },
      showInMenu: false,
      title: (tab, translate) =>
        `${tab.path?.split("/").pop() ?? ""} · ${translate("filePreview.preview")}`,
    },
  ],
};
