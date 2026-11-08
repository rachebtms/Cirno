import { useEffect, useRef, useState } from "react";

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
  const editor = useRef<HTMLTextAreaElement>(null);
  const format = (text: string) => json && text.trim() ? JSON.stringify(JSON.parse(text), null, 2) : text;
  useEffect(() => () => { generation.current += 1; }, []);
  useEffect(() => {
    if (open && !saving && !loading && !loadFailed) editor.current?.focus();
  }, [open, saving, loading, loadFailed, error]);
  const changeOpen = (next: boolean) => {
    if (saving) return;
    const current = ++generation.current;
    setOpen(next);
    setError("");
    setLoadFailed(false);
    setLoading(next && Boolean(loadValue));
    if (!next) return;
    setDraft(value);
    if (loadValue) {
      void loadValue().then(loaded => {
        if (generation.current === current) setDraft(format(loaded));
      }).catch(cause => {
        if (generation.current !== current) return;
        setError(cause instanceof Error ? cause.message : String(cause));
        setLoadFailed(true);
      }).finally(() => { if (generation.current === current) setLoading(false); });
    } else {
      try { setDraft(format(value)); }
      catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    }
  };
  const formatDraft = () => {
    try { setDraft(JSON.stringify(JSON.parse(draft), null, 2)); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
  };
  const save = async () => {
    if (saving || loading || loadFailed) return;
    setSaving(true);
    setError("");
    try {
      await onSave(json ? JSON.stringify(JSON.parse(draft), null, 2) : draft);
      setOpen(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally { setSaving(false); }
  };
  return { open, changeOpen, draft, change: (next: string) => { setDraft(next); setError(""); }, saving, loading, loadFailed, error, editor, formatDraft, save };
}
