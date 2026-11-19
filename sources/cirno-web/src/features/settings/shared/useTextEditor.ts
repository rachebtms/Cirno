import { useEffect, useRef, useState } from "react";
import { useLifetime } from "@/ui/resources/useLifetime";

export function useTextEditor({ value, json, loadValue, onSave }: {
  value: string; json: boolean; loadValue?: () => Promise<string>; onSave: (value: string) => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const isCurrent = useLifetime(undefined);
  const admission = useRef({ open: false, saving: false, loading: false, loadFailed: false });
  const editor = useRef<HTMLTextAreaElement>(null);
  const format = (text: string) => json && text.trim() ? JSON.stringify(JSON.parse(text), null, 2) : text;
  useEffect(() => () => { generation.current += 1; }, []);
  useEffect(() => {
    if (open && !saving && !loading && !loadFailed) editor.current?.focus();
  }, [open, saving, loading, loadFailed, error]);
  const changeOpen = (next: boolean) => {
    if (!isCurrent() || admission.current.saving) return;
    const current = ++generation.current;
    Object.assign(admission.current, { open: next, loading: next && Boolean(loadValue), loadFailed: false });
    setOpen(next);
    setError("");
    setLoadFailed(false);
    setLoading(next && Boolean(loadValue));
    if (!next) return;
    setDraft(value);
    if (loadValue) {
      void (async () => loadValue())().then(loaded => {
        if (isCurrent() && generation.current === current) setDraft(format(loaded));
      }).catch(cause => {
        if (!isCurrent() || generation.current !== current) return;
        admission.current.loadFailed = true;
        setError(cause instanceof Error ? cause.message : String(cause));
        setLoadFailed(true);
      }).finally(() => {
        if (isCurrent() && generation.current === current) {
          admission.current.loading = false;
          setLoading(false);
        }
      });
    } else {
      try { setDraft(format(value)); }
      catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    }
  };
  const formatDraft = () => {
    if (!isCurrent() || !admission.current.open || admission.current.saving || admission.current.loading) return;
    try { setDraft(JSON.stringify(JSON.parse(draft), null, 2)); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
  };
  const save = async () => {
    const gate = admission.current;
    if (!isCurrent() || !gate.open || gate.saving || gate.loading || gate.loadFailed) return;
    gate.saving = true;
    const current = generation.current;
    setSaving(true);
    setError("");
    try {
      await onSave(json ? JSON.stringify(JSON.parse(draft), null, 2) : draft);
      if (isCurrent() && generation.current === current) {
        gate.open = false;
        setOpen(false);
      }
    } catch (cause) {
      if (isCurrent() && generation.current === current)
        setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      gate.saving = false;
      if (isCurrent() && generation.current === current) setSaving(false);
    }
  };
  return { open, changeOpen, draft, change: (next: string) => {
    const gate = admission.current;
    if (!isCurrent() || !gate.open || gate.saving || gate.loading || gate.loadFailed) return;
    setDraft(next); setError("");
  }, saving, loading, loadFailed, error, editor, formatDraft, save };
}
