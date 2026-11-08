import { Alert, Button, SearchField, Spinner } from "@heroui/react";
import { Hint } from "@/ui/feedback/Hint";
import { ChevronUp, Eye, EyeOff, File, FilePlus, Folder, FolderPlus, RefreshCw, Search } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { DirectoryModel, FileEntry } from "../model/useDirectory";
import { CreateEntryDialog } from "./CreateEntryDialog";

export function DirectoryView({ model, onOpenFile }: { model: DirectoryModel; onOpenFile: (path: string) => void }) {
  const { t } = useTranslation();
  const [creating, setCreating] = useState<FileEntry["kind"] | null>(null);
  const open = (entry: FileEntry) => entry.kind === "directory" ? model.navigate(entry.path) : onOpenFile(entry.path);
  return <section className="files-directory" aria-label={t("workspace.files")} aria-busy={model.loading}>
    <header className="files-toolbar">
      <Hint delay={400} content={t("files.parent")}><Button isIconOnly variant="ghost" aria-label={t("files.parent")} isDisabled={!model.directory?.parent || model.loading}
        onPress={() => { if (model.directory?.parent) model.navigate(model.directory.parent); }}><ChevronUp size={18} /></Button></Hint>
      <div className="files-location" title={model.directory?.path ?? model.path}><Folder size={17} /><span>{model.directory?.path ?? model.path}</span></div>
      <Button isIconOnly variant="ghost" aria-label={t("files.refresh")} isDisabled={model.loading} onPress={model.refresh}><RefreshCw size={17} /></Button>
      <Button isIconOnly variant={model.showHidden ? "secondary" : "ghost"} aria-label={t("files.hidden")} aria-pressed={model.showHidden}
        onPress={() => model.setShowHidden(!model.showHidden)}>{model.showHidden ? <EyeOff size={18} /> : <Eye size={18} />}</Button>
    </header>
    <SearchField className="files-search" aria-label={t("files.search")} value={model.query} onChange={model.setQuery}>
      <SearchField.Group><Search size={17} /><SearchField.Input placeholder={t("files.search")} /><SearchField.ClearButton /></SearchField.Group>
    </SearchField>
    {model.error && <Alert status="danger" role="alert"><Alert.Content><Alert.Description>{model.error}</Alert.Description></Alert.Content><Button variant="ghost" onPress={model.refresh}>{t("files.refresh")}</Button></Alert>}
    <div className="files-entry-list">
      {model.loading && <div className="files-loading" role="status"><Spinner size="sm" /><span>{t("workspace.loading")}</span></div>}
      {model.directory?.entries.map(entry => <Button key={entry.path} variant="ghost" className="files-entry" isDisabled={model.loading} onPress={() => open(entry)}>
        {entry.kind === "directory" ? <Folder size={19} /> : <File size={19} />}<span title={entry.path}>{entry.name}</span>
      </Button>)}
      {!model.loading && !model.directory?.entries.length && !model.error && <p className="files-empty">{t("files.empty")}</p>}
      {model.directory?.truncated && <p className="files-empty">{t("files.limited")}</p>}
    </div>
    <footer className="files-footer"><Button variant="ghost" isDisabled={!model.directory || model.loading} onPress={() => setCreating("file")}><FilePlus size={17} />{t("files.newFile")}</Button>
      <Button variant="ghost" isDisabled={!model.directory || model.loading} onPress={() => setCreating("directory")}><FolderPlus size={17} />{t("files.newFolder")}</Button></footer>
    {creating && <CreateEntryDialog kind={creating} directory={model} onClose={() => setCreating(null)} onCreated={open} />}
  </section>;
}
