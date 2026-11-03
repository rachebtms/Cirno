import { useId, useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

interface InlineMessageEditorProps {
  value: string;
  busy: boolean;
  error: string;
  hasToolEffects: boolean;
  onChange: (value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
}

/** Edit the original prompt in place, retaining its attachments and position. */
export function InlineMessageEditor({ value, busy, error, hasToolEffects, onChange, onCancel, onSubmit }: InlineMessageEditorProps) {
  const { t } = useTranslation();
  const input = useRef<HTMLTextAreaElement>(null);
  const descriptionId = useId();
  const warningId = useId();
  useLayoutEffect(() => {
    const element = input.current;
    if (!element) return;
    element.focus({ preventScroll: true });
    element.setSelectionRange(element.value.length, element.value.length);
  }, []);
  useLayoutEffect(() => {
    const element = input.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${element.scrollHeight}px`;
  }, [value]);

  return <form aria-label={t("message.edit")} data-inline-message-editor
    className="w-full min-w-0 rounded-floating bg-secondary/70 p-4"
    onSubmit={event => { event.preventDefault(); if (!busy && value.trim()) onSubmit(); }}>
    <p id={descriptionId} className="sr-only">{t("thread.historyEdit.description")}</p>
    <textarea ref={input} aria-label={t("thread.historyEdit.text")}
      aria-describedby={`${descriptionId}${hasToolEffects ? ` ${warningId}` : ""}`}
      value={value} disabled={busy} onChange={event => onChange(event.target.value)}
      onKeyDown={event => {
        if (event.nativeEvent.isComposing || event.keyCode === 229) return;
        if (event.key === "Escape" && !busy) { event.preventDefault(); event.stopPropagation(); onCancel(); }
        if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
          event.preventDefault();
          if (!busy && value.trim()) onSubmit();
        }
      }}
      className="touch-text-input block min-h-24 max-h-[50dvh] w-full resize-none border-0 bg-transparent p-0 text-reading [overflow-wrap:anywhere] focus:outline-none disabled:opacity-60" />
    {hasToolEffects ? <p id={warningId} role="note" className="mt-3 text-sm text-destructive [overflow-wrap:anywhere]">{t("thread.historyEffects.description")}</p> : null}
    {error ? <p role="alert" className="mt-3 text-sm text-destructive [overflow-wrap:anywhere]">{error}</p> : null}
    <div className="mt-4 flex flex-wrap justify-end gap-2">
      <Button type="button" variant="outline" disabled={busy} onClick={onCancel}>{t("files.cancel")}</Button>
      <Button type="submit" disabled={busy || !value.trim()}>{t("thread.historyEdit.submit")}</Button>
    </div>
  </form>;
}
