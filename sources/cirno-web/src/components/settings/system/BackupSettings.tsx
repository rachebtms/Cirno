import { useEffect, useRef, useState } from "react";
import { Download, Upload, Plus, Folder, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CirnoClient } from "@/lib/cirno-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SettingsGroup, SettingsRow, SettingsSectionTitle } from "@/components/settings/shared/SettingsControls";

type Catalog = { instance: string; selected: string[]; pending_restore: boolean; recommended: { path: string; kind: string; included: boolean; directory: boolean }[] };
type Manifest = { id: string; version: string; created_at: string; instance: string; extras: { archive: string; path: string; directory: boolean }[] };

export function BackupSettings({ client, onRestart }: { client: CirnoClient; onRestart: () => void | Promise<void> }) {
  const { t } = useTranslation();
  const tr = (key: string) => t(`settings.backup.${key}`);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [paths, setPaths] = useState<string[]>([]);
  const [custom, setCustom] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [download, setDownload] = useState<{ url: string; filename: string } | null>(null);
  const [preview, setPreview] = useState<Manifest | null>(null);
  const [targets, setTargets] = useState<Record<string, string>>({});
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => {
    let active = true;
    void client.backupRequest<Catalog>("catalog").then((value) => {
      if (active) { setCatalog(value); setPaths(value.selected); }
    }).catch((err: Error) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [client]);
  const toggle = (path: string) => setPaths((items) => items.includes(path) ? items.filter((item) => item !== path) : [...items, path]);
  const run = async (work: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await work(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  const exportBackup = () => run(async () => {
    const value = await client.backupRequest<{ url: string; filename: string }>("export", { paths });
    setDownload(value);
    const link = document.createElement("a"); link.href = value.url; link.download = value.filename; link.click();
  });
  const importBackup = (backup: File) => run(async () => {
    const value = await client.backupRequest<Manifest>("upload", backup);
    setTargets(Object.fromEntries(value.extras.map((item) => [item.archive, item.path])));
    setPreview(value);
  });
  const closePreview = () => {
    if (busy) return;
    if (preview) void run(async () => { await client.backupRequest("cancel", { id: preview.id }); setPreview(null); });
  };
  return <div className="settings-stack">
    {error && <p role="alert" className="settings-list-inset break-words text-sm text-destructive">{error}</p>}
    <section><SettingsSectionTitle>{tr("instance")}</SettingsSectionTitle><SettingsGroup>
      <SettingsRow title={tr("everything")} description={tr("everythingHelp")}>
        <p className="break-all text-xs text-muted-foreground">{catalog?.instance ?? "…"}</p>
      </SettingsRow>
    </SettingsGroup><p className="settings-list-inset mt-3 text-sm leading-6 text-muted-foreground">{tr("credentials")}</p></section>
    <section><SettingsSectionTitle>{tr("extra")}</SettingsSectionTitle>
      <p className="settings-list-inset mb-3 text-sm text-muted-foreground">{tr("extraHelp")}</p>
      <SettingsGroup>{(catalog?.recommended ?? []).map((item) => <SettingsRow inline key={item.path} title={<span className="flex min-w-0 items-start gap-2"><Folder className="mt-0.5 h-4 w-4 shrink-0" /><span className="break-all">{item.path}</span></span>}
        description={item.included ? tr("included") : tr(item.kind === "workspace" ? "workspace" : "toolData")}>
        <input type="checkbox" aria-label={item.path} checked={item.included || paths.includes(item.path)} disabled={busy || item.included}
          onChange={() => toggle(item.path)} className="h-4 w-4 shrink-0 accent-current" />
      </SettingsRow>)}
      {paths.filter((path) => !catalog?.recommended.some((item) => item.path === path)).map((path) => <SettingsRow inline key={path} title={<span className="break-all">{path}</span>}>
        <Button variant="ghost" size="icon" aria-label={`${tr("remove")} ${path}`} disabled={busy} onClick={() => toggle(path)}><X className="h-4 w-4" /></Button>
      </SettingsRow>)}
      <div className="flex min-w-0 gap-2 p-4"><Input aria-label={tr("path")} placeholder={tr("path")} value={custom} onChange={(event) => setCustom(event.target.value)} disabled={busy} className="min-w-0" />
        <Button variant="outline" size="icon" aria-label={tr("add")} disabled={busy || !custom.trim()} onClick={() => { setPaths((items) => [...new Set([...items, custom.trim()])]); setCustom(""); }}><Plus className="h-4 w-4" /></Button>
      </div>
      </SettingsGroup>
    </section>
    <div className="flex flex-wrap gap-3 settings-list-inset">
      <Button disabled={busy || !catalog} onClick={() => void exportBackup()}><Download className="mr-2 h-4 w-4" />{tr(busy ? "working" : "export")}</Button>
      <Button variant="outline" disabled={busy || !catalog} onClick={() => file.current?.click()}><Upload className="mr-2 h-4 w-4" />{tr("import")}</Button>
      <input ref={file} type="file" accept=".gz,.tgz,application/gzip" hidden aria-label={tr("import")} onChange={(event) => {
        const selected = event.target.files?.[0]; event.target.value = ""; if (selected) void importBackup(selected);
      }} />
      {download && <a href={download.url} download={download.filename} className="self-center break-all text-sm text-content-link underline">{tr("downloadReady")}</a>}
    </div>
    {catalog?.pending_restore && <div className="settings-list-inset space-y-3 text-sm"><p>{tr("pending")}</p><Button onClick={() => void onRestart()}>{tr("restart")}</Button><Button variant="outline" className="ml-2" onClick={() => void run(async () => { await client.backupRequest("cancel"); setCatalog({ ...catalog, pending_restore: false }); })}>{tr("cancel")}</Button></div>}
    <Dialog open={preview !== null} onOpenChange={(open) => { if (!open) closePreview(); }}><DialogContent className="max-w-xl">
      <DialogHeader><DialogTitle>{tr("restoreTitle")}</DialogTitle><DialogDescription>{tr("restoreHelp")}</DialogDescription></DialogHeader>
      {preview && <div className="space-y-4 text-sm"><p>{tr("version")}: {preview.version} · {new Date(preview.created_at).toLocaleString()}</p>
        <p className="break-all">{tr("source")}: {preview.instance}</p><p className="break-all">{tr("destination")}: {catalog?.instance}</p>
        {preview.extras.map((item) => <label key={item.archive} className="block space-y-1"><span className="break-all">{item.path}</span>
          <Input aria-label={item.path} value={targets[item.archive] ?? ""} placeholder={tr("skip")} onChange={(event) => setTargets((value) => ({ ...value, [item.archive]: event.target.value }))} disabled={busy} /></label>)}
        <p className="text-muted-foreground">{tr("extrasRestore")}</p>
        {error && <p role="alert" className="break-words text-destructive">{error}</p>}
      </div>}
      <DialogFooter><Button variant="outline" disabled={busy} onClick={closePreview}>{tr("cancel")}</Button>
        <Button disabled={busy} onClick={() => preview && void run(async () => {
          await client.backupRequest("restore", { id: preview.id, extras: targets });
          setPreview(null); setCatalog((value) => value && { ...value, pending_restore: true }); await onRestart();
        })}>{tr("restore")}</Button></DialogFooter>
    </DialogContent></Dialog>
  </div>;
}
