import { useDeferredValue, useEffect, useMemo, useState } from "react";
import type { CirnoClient } from "@/lib/cirno-client";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import { documentDirty, useFileDocument } from "../documents";

export interface DocumentViewProps {
  client: CirnoClient; path: string; sessionKey: string | null; scope?: WorkspaceScopePayload | null;
  preview?: boolean; active?: boolean; initialEditing?: boolean;
  onBack?: () => void; onOpenPreview?: () => void; onOpenFile?: (path: string) => void;
  onReplaceFile?: (path: string) => void; onDirtyChange?: (dirty: boolean) => void;
  onRegisterClose?: (close: () => Promise<void>) => void;
}
export function useDocumentView(props: DocumentViewProps) {
  const { document, state } = useFileDocument(props.client, props.path, props.sessionKey, props.scope, !!props.preview);
  const [editing, setEditing] = useState((props.initialEditing ?? true) && !props.preview);
  const [imageOpen, setImageOpen] = useState(false);
  const [mediaError, setMediaError] = useState("");
  const [pending, setPending] = useState<(() => void) | null>(null);
  const dirty = documentDirty(state);
  const ownsDraft = dirty && !props.preview;
  const draft = useDeferredValue(state.draft);
  const payload = useMemo(() => state.file?.kind === "text" ? { ...state.file, content: draft } : state.file, [state.file, draft]);
  useEffect(() => setMediaError(""), [state.file]);
  useEffect(() => { props.onDirtyChange?.(ownsDraft); return () => props.onDirtyChange?.(false); }, [ownsDraft, props.onDirtyChange]);
  useEffect(() => {
    if (!ownsDraft) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [ownsDraft]);
  useEffect(() => {
    props.onRegisterClose?.(async () => {
      const saving = document.snapshot().saving;
      await document.settled();
      if (saving && document.snapshot().error) throw new Error(document.snapshot().error);
    });
  }, [document, props.onRegisterClose]);
  const guard = (action: () => void) => { if (ownsDraft) setPending(() => action); else action(); };
  const discard = () => { document.discard(); pending?.(); setPending(null); };
  return { document, state, dirty, editing, setEditing, imageOpen, setImageOpen, mediaError, setMediaError, pending, setPending, payload, guard, discard };
}
export type DocumentViewModel = ReturnType<typeof useDocumentView>;
