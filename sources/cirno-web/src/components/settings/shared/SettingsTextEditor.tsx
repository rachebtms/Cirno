import { useEffect, useRef, useState, type ReactElement } from "react";
import { SquarePen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { HoverHint } from "@/components/ui/tooltip";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export function SettingsTextEditor({ id, title, description, value, placeholder, disabled, trigger, onSave, saveLabel, buttonLabel, json = false, loadValue }: {
  id?: string;
  title: string;
  description?: string;
  value: string;
  placeholder?: string;
  disabled?: boolean;
  trigger?: ReactElement;
  onSave: (value: string) => void | Promise<void>;
  saveLabel?: string;
  buttonLabel?: string;
  json?: boolean;
  loadValue?: () => Promise<string>;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const loadId = useRef(0);
  const [error, setError] = useState("");
  const editor = useRef<HTMLTextAreaElement>(null);
  const help = description?.trim();
  const hasDescription = !!help && help !== title.trim();
  useEffect(() => {
    if (error && !saving) editor.current?.focus();
  }, [error, saving]);
  useEffect(() => {
    if (open && !loading && !loadFailed) {
      editor.current?.focus();
      editor.current?.setSelectionRange(0, 0);
      if (editor.current) editor.current.scrollTop = 0;
    }
  }, [open, loading, loadFailed]);
  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await onSave(json ? JSON.stringify(JSON.parse(draft), null, 2) : draft);
      setOpen(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  };
  return <Dialog open={open} onOpenChange={(next) => {
    if (saving) return;
    const currentLoad = ++loadId.current;
    setError("");
    setLoadFailed(false);
    setLoading(next && Boolean(loadValue));
    if (next) {
      setDraft(value);
      if (loadValue) {
        void loadValue().then((loaded) => {
          if (loadId.current === currentLoad) setDraft(json ? JSON.stringify(JSON.parse(loaded), null, 2) : loaded);
        }).catch((cause) => {
          if (loadId.current === currentLoad) {
            setError(cause instanceof Error ? cause.message : String(cause));
            setLoadFailed(true);
          }
        }).finally(() => {
          if (loadId.current === currentLoad) setLoading(false);
        });
      } else if (json && value.trim()) {
        try { setDraft(JSON.stringify(JSON.parse(value), null, 2)); }
        catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
      }
    }
    setOpen(next);
  }}>
    {trigger ? <DialogTrigger asChild id={id} disabled={disabled}>{trigger}</DialogTrigger> : <HoverHint content={t("settings.actions.edit")}>
      <DialogTrigger asChild>
        <Button data-settings-inline-action size="icon" id={id} type="button" variant="ghost" disabled={disabled} aria-label={buttonLabel ?? title}
          className="ml-auto flex h-9 w-9 shrink-0 rounded-full p-0 text-muted-foreground">
          <SquarePen className="h-4 w-4" aria-hidden />
        </Button>
      </DialogTrigger>
    </HoverHint>}
    <DialogContent className="max-w-xl" showCloseButton={!saving}
      {...(hasDescription ? {} : { "aria-describedby": undefined })}
      onOpenAutoFocus={(event) => { event.preventDefault(); editor.current?.focus(); }}
      onEscapeKeyDown={(event) => { if (saving) event.preventDefault(); }}
      onPointerDownOutside={(event) => { if (saving) event.preventDefault(); }}>
      <DialogHeader>
        <DialogTitle className="pr-6 text-base">{title}</DialogTitle>
        {hasDescription && <DialogDescription>{help}</DialogDescription>}
      </DialogHeader>
      <Textarea ref={editor} aria-label={buttonLabel ?? title} value={draft} placeholder={placeholder} disabled={saving || loading || loadFailed}
        aria-busy={loading}
        aria-invalid={Boolean(error)} spellCheck={false}
        onChange={(event) => { setDraft(event.target.value); setError(""); }}
        className="h-[min(40vh,280px)] min-h-24 resize-none rounded-control font-mono text-[13px] leading-6" />
      {loading && <p role="status" className="text-[13px] text-muted-foreground">{t("settings.loading")}</p>}
      {error && <p role="alert" className="break-words text-[13px] text-destructive">{error}</p>}
      <DialogFooter>
        {json && <Button type="button" variant="ghost" disabled={saving || loading || loadFailed} className="sm:mr-auto" onClick={() => {
          try { setDraft(JSON.stringify(JSON.parse(draft), null, 2)); setError(""); }
          catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
        }}>{t("settings.actions.formatJson", { defaultValue: "Format JSON" })}</Button>}
        <Button type="button" variant="outline" disabled={saving} onClick={() => setOpen(false)}>{t("settings.actions.cancel")}</Button>
        <Button type="button" disabled={saving || loading || loadFailed} onClick={() => void save()}>{saving ? t("settings.actions.saving") : saveLabel ?? t("settings.actions.save")}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>;
}
