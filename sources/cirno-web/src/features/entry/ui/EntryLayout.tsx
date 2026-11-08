import type { ReactNode } from "react";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useTheme } from "@/hooks/useTheme";
import "../entry.css";

export function EntryLayout({ title, description, step, children, footer }: {
  title: string; description?: string; step?: string; children: ReactNode; footer?: ReactNode;
}) {
  useTheme();
  return <main className="entry-screen">
    <header className="entry-header"><LanguageSwitcher /></header>
    <div className="entry-body"><section className="entry-form" aria-labelledby="entry-title">
      <img className="entry-mark" src="/brand/cirno_snowflake_mark.svg" width={56} height={56} alt="" />
      {step && <p className="entry-step">{step}</p>}
      <h1 id="entry-title">{title}</h1>
      {description && <p className="entry-description">{description}</p>}
      {children}
      {footer && <footer className="entry-footnote">{footer}</footer>}
    </section></div>
  </main>;
}
