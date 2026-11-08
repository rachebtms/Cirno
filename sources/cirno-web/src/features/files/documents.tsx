import type { CirnoClient } from "@/lib/cirno-client";
import type { FilePreviewPayload } from "@/lib/contracts/files";
import type { WorkspaceScopePayload } from "@/lib/contracts/workspaces";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { fileRequest } from "./api";

export type EditableFile = FilePreviewPayload & {
  editable: boolean;
  revision: string | null;
};
export interface FileDocumentState {
  file?: EditableFile;
  draft: string;
  loading: boolean;
  saving: boolean;
  error: string;
}
export function documentDirty(state: FileDocumentState) {
  return (
    state.file?.kind === "text" &&
    state.file.editable &&
    state.draft !== state.file.content
  );
}

export class FileDocument {
  private state: FileDocumentState = {
    draft: "",
    loading: false,
    saving: false,
    error: "",
  };
  private listeners = new Set<() => void>();
  private pending: Promise<void> | null = null;
  readers = 0;
  editors = 0;
  constructor(
    private path: string,
    private request: ReturnType<typeof fileRequest>,
  ) {}
  snapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private update(values: Partial<FileDocumentState>) {
    this.state = { ...this.state, ...values };
    this.listeners.forEach((listener) => listener());
  }
  edit = (draft: string) => {
    if (!this.state.file?.editable || this.state.saving || this.state.loading)
      throw new Error("This file cannot be edited now");
    this.update({ draft });
  };
  discard = () =>
    this.update({
      draft: this.state.file?.kind === "text" ? this.state.file.content : "",
    });
  load = (): Promise<void> => this.operation("read");
  settled = (): Promise<void> => this.pending ?? Promise.resolve();
  save = (): Promise<void> => {
    if (!documentDirty(this.state)) return Promise.resolve();
    return this.operation("save");
  };
  private operation(action: "read" | "save"): Promise<void> {
    if (this.pending) return this.pending;
    const values =
      action === "save"
        ? {
            path: this.path,
            content: this.state.draft,
            revision: this.state.file?.revision,
          }
        : { path: this.path };
    this.update({
      error: "",
      loading: action === "read",
      saving: action === "save",
    });
    this.pending = Promise.resolve().then(async () => {
      try {
        const file = await this.request<EditableFile>(action, values);
        this.update({ file, draft: file.kind === "text" ? file.content : "" });
      } catch (error) {
        this.update({
          error: error instanceof Error ? error.message : String(error),
        });
      } finally {
        this.pending = null;
        this.update({ loading: false, saving: false });
      }
    });
    return this.pending;
  }
}

export class FileDocuments {
  private entries = new Map<string, FileDocument>();
  document(key: string, create: () => FileDocument) {
    let entry = this.entries.get(key);
    if (!entry) {
      entry = create();
      this.entries.set(key, entry);
    }
    return entry;
  }
  retain(key: string, document: FileDocument, editor: boolean) {
    this.entries.set(key, document);
    document.readers += 1;
    if (editor) document.editors += 1;
    if (!document.snapshot().file) void document.load();
    return () => {
      document.readers -= 1;
      if (editor && --document.editors === 0) document.discard();
      void document.settled().then(() => {
        if (!document.readers && this.entries.get(key) === document)
          this.entries.delete(key);
      });
    };
  }
}
const DocumentsContext = createContext<FileDocuments | null>(null);
export function FileDocumentsProvider({ children }: { children: ReactNode }) {
  const [documents] = useState(() => new FileDocuments());
  return (
    <DocumentsContext.Provider value={documents}>
      {children}
    </DocumentsContext.Provider>
  );
}

export function useFileDocument(
  client: CirnoClient,
  path: string,
  sessionKey: string | null,
  scope: WorkspaceScopePayload | null | undefined,
  preview: boolean,
) {
  const shared = useContext(DocumentsContext);
  const [local] = useState(() => new FileDocuments());
  const documents = shared ?? local;
  const key = JSON.stringify([
    sessionKey,
    scope?.project_path,
    scope?.access_mode,
    path,
  ]);
  const document = useMemo(
    () =>
      documents.document(
        key,
        () => new FileDocument(path, fileRequest(client, sessionKey, scope)),
      ),
    [client, documents, key, path, sessionKey, scope],
  );
  useEffect(
    () => documents.retain(key, document, !preview),
    [documents, key, document, preview],
  );
  return {
    document,
    state: useSyncExternalStore(
      document.subscribe,
      document.snapshot,
      document.snapshot,
    ),
  };
}
