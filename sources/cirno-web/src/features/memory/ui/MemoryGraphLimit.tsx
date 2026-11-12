import { FieldError, Input, Label, TextField } from "@heroui/react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { patchPreferences, readPreferenceStatus } from "@/features/preferences/store";
import { useLifetime } from "@/ui/resources/useLifetime";

export function MemoryGraphLimit({ value }: { value: number }) {
  const { t } = useTranslation();
  const isCurrent = useLifetime(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const pending = useRef(false);
  const commit = async () => {
    if (draft === null || pending.current) return;
    const count = Number(draft);
    if (!Number.isSafeInteger(count) || count < 1) {
      setError(t("memoryGraph.limitError"));
      return;
    }
    if (count === value) { setDraft(null); return; }
    const submitted = draft;
    pending.current = true;
    setError("");
    setSaving(true);
    const saved = await patchPreferences({ memoryGraphLimit: count });
    pending.current = false;
    if (!isCurrent()) return;
    setSaving(false);
    if (saved) setDraft(current => current === submitted ? null : current);
    else setError(readPreferenceStatus().error);
  };
  return <form className="memory-graph-limit" noValidate onSubmit={event => { event.preventDefault(); void commit(); }}>
    <TextField className="memory-graph-limit-field" value={draft ?? String(value)}
      isDisabled={saving} isInvalid={!!error} onBlur={() => { void commit(); }}
      onChange={next => { setDraft(next); setError(""); }}>
      <Label>{t("memoryGraph.nodeLimit")}</Label>
      <Input type="number" min={1} max={Number.MAX_SAFE_INTEGER} step={1} />
      <FieldError className="memory-graph-limit-error">{error}</FieldError>
    </TextField>
  </form>;
}
