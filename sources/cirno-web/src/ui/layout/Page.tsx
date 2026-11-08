import type { ReactNode, Ref } from "react";
import "./page.css";
export function Page({ children, label, className = "", ref, busy }: { children: ReactNode; label: string; className?: string; ref?: Ref<HTMLElement>; busy?: boolean }) {
  return <section ref={ref} aria-label={label} aria-busy={busy || undefined} className={`feature-page ${className}`}><div className="feature-page-content">{children}</div></section>;
}
export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return <header className="feature-page-header"><div className="feature-page-heading"><h1>{title}</h1>{description && <p>{description}</p>}</div>
    {actions && <div className="feature-page-actions">{actions}</div>}</header>;
}
export function EmptyState({ icon, title, action }: { icon: ReactNode; title: string; action?: ReactNode }) {
  return <div className="feature-empty">{icon}<p>{title}</p>{action}</div>;
}
