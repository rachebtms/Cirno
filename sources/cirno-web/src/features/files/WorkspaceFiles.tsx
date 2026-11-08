import { useState } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { FileDocumentView } from "./FileDocumentView";
import { useDirectory } from "./model/useDirectory";
import { DirectoryView } from "./ui/DirectoryView";
import "./files.css";

export function WorkspaceFiles({ client, sessionKey, workspaceScope, onDirtyChange, onOpenFile }: {
  client: CirnoClient; sessionKey: string | null; workspaceScope?: WorkspaceScopePayload | null;
  onDirtyChange?: (dirty: boolean) => void; onOpenFile?: (path: string) => void;
}) {
  const directory = useDirectory(client, sessionKey, workspaceScope);
  const [selected, setSelected] = useState<string | null>(null);
  if (selected) return <FileDocumentView key={selected} client={client} path={selected} sessionKey={sessionKey}
    scope={workspaceScope} initialEditing={false} onBack={() => setSelected(null)} onReplaceFile={setSelected} onDirtyChange={onDirtyChange} />;
  return <DirectoryView model={directory} onOpenFile={onOpenFile ?? setSelected} />;
}
