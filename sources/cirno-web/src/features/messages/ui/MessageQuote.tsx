import { Quote } from "lucide-react";

export function MessageQuote({ text, label }: { text: string; label: string }) {
  return (
    <blockquote
      data-theme-surface
      data-theme-ink
      aria-label={label}
      className="message-quote"
    >
      <Quote size={14} aria-hidden />
      <p>{text}</p>
    </blockquote>
  );
}
