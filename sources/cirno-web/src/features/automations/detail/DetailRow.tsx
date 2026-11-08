import type { ReactNode } from "react";

export function DetailRow({
  label,
  title,
  children,
}: {
  label: ReactNode;
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className="automation-detail-row">
      <dt>{label}</dt>
      <dd title={title}>{children}</dd>
    </div>
  );
}
