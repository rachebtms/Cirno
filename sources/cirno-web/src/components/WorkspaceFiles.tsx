import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ChevronUp,
  Eye,
  File,
  FilePlus,
  Folder,
  FolderPlus,
  RefreshCw,
  Save,
  SquarePen,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { FilePreviewPanelView } from "@/components/FilePreviewPanelView";
import type { CirnoClient } from "@/lib/cirno-client";
import type { FilePreviewPayload, WorkspaceScopePayload } from "@/lib/types";
import { cn } from "@/lib/utils";

type Entry = { name: string; path: string; kind: "file" | "directory" };
type Directory = {
  path: string;
  project_path: string;
  parent: string | null;
  entries: Entry[];
  truncated: boolean;
};
type Preview = FilePreviewPayload & {
  editable: boolean;
  revision: string | null;
};

export function WorkspaceFiles({
  client,
  sessionKey,
  workspaceScope,
  onDirtyChange,
}: {
  client: CirnoClient;
  sessionKey: string | null;
  workspaceScope?: WorkspaceScopePayload | null;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const { t } = useTranslation();
  const tx = (key: string) => t(`files.${key}`);
  const [directoryPath, setDirectoryPath] = useState(
    workspaceScope?.project_path ?? "",
  );
  const [directory, setDirectory] = useState<Directory | null>(null);
  const [query, setQuery] = useState("");
  const [showHidden, setShowHidden] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [listing, setListing] = useState(false);
  const [file, setFile] = useState<Preview | null>(null);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [imageOpen, setImageOpen] = useState(false);
  const [newKind, setNewKind] = useState<Entry["kind"] | null>(null);
  const [newName, setNewName] = useState("");
  const [createError, setCreateError] = useState("");
  const [creating, setCreating] = useState(false);
  const [pending, setPending] = useState<(() => void) | null>(null);
  const readSequence = useRef(0);
  const dirty = file?.kind === "text" && draft !== file.content;
  const context = useMemo(
    () => ({
      session_key: sessionKey,
      ...(workspaceScope
        ? {
            workspace_scope: {
              project_path: workspaceScope.project_path,
              access_mode: workspaceScope.access_mode,
            },
          }
        : {}),
    }),
    [sessionKey, workspaceScope?.project_path, workspaceScope?.access_mode],
  );
  const request = useCallback(
    <T,>(action: string, data: Record<string, unknown>) =>
      client.requestMutation<T>(`workspace.files.${action}`, {
        ...context,
        ...data,
      }),
    [client, context],
  );

  useEffect(() => {
    let cancelled = false;
    setListing(true);
    const timer = window.setTimeout(
      () => {
        void request<Directory>("list", {
          path: directoryPath,
          query,
          show_hidden: showHidden,
        })
          .then((value) => {
            if (!cancelled) {
              setDirectory(value);
              setError("");
            }
          })
          .catch((reason: Error) => {
            if (!cancelled) setError(reason.message);
          })
          .finally(() => {
            if (!cancelled) setListing(false);
          });
      },
      query ? 200 : 0,
    );
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [directoryPath, query, showHidden, refresh, request]);
  useEffect(
    () => () => {
      readSequence.current += 1;
    },
    [],
  );
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);

  const guard = (action: () => void) => {
    if (dirty) setPending(() => action);
    else action();
  };
  const loadFile = async (path: string) => {
    const sequence = ++readSequence.current;
    setBusy(true);
    setError("");
    try {
      const value = await request<Preview>("read", { path });
      if (sequence !== readSequence.current) return;
      setFile(value);
      setDraft(value.kind === "text" ? value.content : "");
      setEditing(false);
    } catch (reason) {
      if (sequence === readSequence.current)
        setError((reason as Error).message);
    } finally {
      if (sequence === readSequence.current) setBusy(false);
    }
  };
  const save = async () => {
    if (!file?.editable || !dirty || busy) return;
    setBusy(true);
    setError("");
    try {
      const saved = await request<Preview>("save", {
        path: file.path,
        content: draft,
        revision: file.revision,
      });
      setFile(saved);
      setDraft(saved.kind === "text" ? saved.content : "");
      setRefresh((value) => value + 1);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const navigate = (path: string) => {
    setDirectoryPath(path);
    setQuery("");
  };
  const create = async () => {
    if (!directory || !newName.trim() || !newKind || creating) return;
    setCreating(true);
    setCreateError("");
    try {
      const created = await request<{ path: string; kind: Entry["kind"] }>(
        "create",
        {
          path: `${directory.path}/${newName}`,
          kind: newKind,
        },
      );
      setNewKind(null);
      setNewName("");
      setRefresh((value) => value + 1);
      if (created.kind === "file") await loadFile(created.path);
      else navigate(created.path);
    } catch (reason) {
      setCreateError((reason as Error).message);
    } finally {
      setCreating(false);
    }
  };
  const selectedPreview =
    file?.kind === "text" ? { ...file, content: draft } : file;

  return (
    <>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {error ? (
          <p
            role="alert"
            className="shrink-0 px-3 py-2 break-words text-sm text-destructive"
          >
            {error}
          </p>
        ) : null}
        <div className="flex min-h-0 flex-1 flex-col">
          <section
            className={cn("flex min-h-0 flex-1 flex-col p-3", file && "hidden")}
          >
            <div className="flex shrink-0 items-center gap-1">
              <Button
                size="icon"
                variant="ghost"
                aria-label={tx("parent")}
                disabled={!directory?.parent || listing}
                onClick={() => directory?.parent && navigate(directory.parent)}
              >
                <ChevronUp className="h-4 w-4" />
              </Button>
              <span
                className="min-w-0 flex-1 truncate text-xs"
                title={directory?.path}
              >
                {directory?.path || workspaceScope?.project_path}
              </span>
              <Button
                size="icon"
                variant="ghost"
                aria-label={tx("refresh")}
                disabled={listing}
                onClick={() => setRefresh((value) => value + 1)}
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                aria-label={tx("hidden")}
                aria-pressed={showHidden}
                onClick={() => setShowHidden((value) => !value)}
              >
                <Eye className="h-3.5 w-3.5" />
              </Button>
            </div>
            <Input
              className="my-2 shrink-0"
              aria-label={tx("search")}
              placeholder={tx("search")}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <div className="min-h-0 flex-1 overflow-auto" aria-busy={listing}>
              {directory?.entries.map((entry) => (
                <button
                  key={entry.path}
                  type="button"
                  disabled={busy || listing}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-control px-2 py-2 text-left text-sm hover:bg-muted focus-visible:outline-ring",
                    file?.path === entry.path && "bg-muted",
                  )}
                  onClick={() =>
                    entry.kind === "directory"
                      ? navigate(entry.path)
                      : guard(() => void loadFile(entry.path))
                  }
                >
                  {entry.kind === "directory" ? (
                    <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
                  ) : (
                    <File className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                  <span className="truncate" title={entry.name}>
                    {entry.name}
                  </span>
                </button>
              ))}
              {!listing && !directory?.entries.length ? (
                <p className="p-3 text-sm text-muted-foreground">
                  {tx("empty")}
                </p>
              ) : null}
              {directory?.truncated ? (
                <p className="p-2 text-xs text-muted-foreground">
                  {tx("limited")}
                </p>
              ) : null}
            </div>
            <div className="mt-2 flex shrink-0 gap-2">
              {(["file", "directory"] as const).map((kind) => (
                <Button
                  key={kind}
                  variant="ghost"
                  size="sm"
                  disabled={!directory || busy}
                  onClick={() =>
                    guard(() => {
                      setNewKind(kind);
                      setNewName("");
                      setCreateError("");
                    })
                  }
                >
                  {kind === "file" ? (
                    <FilePlus className="mr-1 h-3.5 w-3.5" />
                  ) : (
                    <FolderPlus className="mr-1 h-3.5 w-3.5" />
                  )}
                  {tx(kind === "file" ? "newFile" : "newFolder")}
                </Button>
              ))}
            </div>
          </section>
          <section
            className={cn(
              "flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden",
              !file && "hidden",
            )}
          >
            {file ? (
              <>
                <div className="flex shrink-0 items-center gap-1 border-b border-border/50 px-2 py-1.5">
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={tx("back")}
                    disabled={busy}
                    onClick={() =>
                      guard(() => {
                        setFile(null);
                        setDraft("");
                      })
                    }
                  >
                    <ArrowLeft className="h-4 w-4" />
                  </Button>
                  <span
                    className="min-w-0 flex-1 truncate text-sm"
                    title={file.path}
                  >
                    {file.display_path}
                    {dirty ? " *" : ""}
                  </span>
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={tx("reloadFile")}
                    disabled={busy}
                    onClick={() => guard(() => void loadFile(file.path))}
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </Button>
                  {file.editable ? (
                    <>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => setEditing((value) => !value)}
                      >
                        <SquarePen className="mr-1 h-3.5 w-3.5" />
                        {tx(editing ? "preview" : "edit")}
                      </Button>
                      <Button
                        size="sm"
                        disabled={!dirty || busy}
                        onClick={() => void save()}
                      >
                        <Save className="mr-1 h-3.5 w-3.5" />
                        {tx("save")}
                      </Button>
                    </>
                  ) : (
                    <span className="px-2 text-xs text-muted-foreground">
                      {tx("readOnly")}
                    </span>
                  )}
                </div>
                {editing ? (
                  <Textarea
                    aria-label={tx("contents")}
                    value={draft}
                    disabled={busy}
                    spellCheck={false}
                    wrap="off"
                    className="min-h-0 flex-1 resize-none rounded-none border-0 bg-transparent p-4 font-mono text-sm leading-6 focus-visible:ring-0"
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (
                        (event.metaKey || event.ctrlKey) &&
                        event.key.toLowerCase() === "s"
                      ) {
                        event.preventDefault();
                        void save();
                      }
                    }}
                  />
                ) : selectedPreview ? (
                  <div className="relative flex min-h-0 flex-1 flex-col">
                    <FilePreviewPanelView
                      path={file.path}
                      state={{ status: "ready", payload: selectedPreview }}
                      imageOpen={imageOpen}
                      onImageOpenChange={setImageOpen}
                      onImageError={() => setError(tx("imageError"))}
                      onOpenFilePreview={(path) =>
                        guard(() => void loadFile(path))
                      }
                    />
                  </div>
                ) : null}
              </>
            ) : (
              <p className="m-auto p-5 text-sm text-muted-foreground">
                {tx("choose")}
              </p>
            )}
          </section>
        </div>
      </div>
      <Dialog
        open={newKind !== null}
        onOpenChange={(value) => {
          if (!value && !creating) setNewKind(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {tx(newKind === "directory" ? "newFolder" : "newFile")}
            </DialogTitle>
            <DialogDescription>{directory?.path}</DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void create();
            }}
            className="space-y-4"
          >
            <Input
              autoFocus
              aria-label={tx("name")}
              value={newName}
              disabled={creating}
              onChange={(event) => setNewName(event.target.value)}
            />
            {createError ? (
              <p role="alert" className="text-sm text-destructive">
                {createError}
              </p>
            ) : null}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={creating}
                onClick={() => setNewKind(null)}
              >
                {tx("cancel")}
              </Button>
              <Button disabled={!newName.trim() || creating}>
                {tx("create")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <AlertDialog
        open={pending !== null}
        onOpenChange={(value) => {
          if (!value) setPending(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{tx("discardTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {tx("discardDescription")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tx("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setDraft(file?.kind === "text" ? file.content : "");
                setEditing(false);
                pending?.();
                setPending(null);
              }}
            >
              {tx("discard")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
