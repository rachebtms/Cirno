import type { ReactNode } from "react";
import type { ChannelRuntimeStatus } from "@/lib/contracts/channels";
export function ChannelStatusBadge({
  children,
  status,
}: {
  children: ReactNode;
  status?: ChannelRuntimeStatus;
}) {
  return (
    <span
      className={[
        "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium leading-4",
        status === "failed"
          ? "bg-destructive/10 text-destructive"
          : status === "running"
            ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-200"
            : "bg-surface-secondary/75 text-muted-foreground",
      ].join(" ")}
    >
      {children}
    </span>
  );
}
