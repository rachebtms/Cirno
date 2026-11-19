import { floatingSurfaceElevationClassName } from "@/components/ui/floating-surface";
import { cn } from "@/lib/utils";
import { Suspense } from "react";
import { DeleteConfirm } from "./navigation";
import type { ShellSurfaceProps } from "./surface-contract";
export function WorkspaceDialogs({
  workspaceState,
  navigationActions,
}: Pick<
  ShellSurfaceProps,
  "workspaceState" | "navigationActions"
>) {
  const {
    pendingDelete,
    client,
    restartToast,
  } = workspaceState;
  const {
    onConfirmDelete,
    onCancelDelete,
    deleteBusy,
    deleteError,
  } = navigationActions;
  return (
    <>
      {pendingDelete && pendingDelete.owner === client ? (
        <Suspense fallback={null}>
          <DeleteConfirm
            open
            title={pendingDelete.items[0]?.label ?? ""}
            count={pendingDelete.items.length}
            automations={pendingDelete.automations}
            busy={deleteBusy}
            error={deleteError}
            onCancel={onCancelDelete}
            onConfirm={onConfirmDelete}
          />
        </Suspense>
      ) : null}
      {restartToast ? (
        <div className="fixed left-1/2 top-[calc(0.75rem+env(safe-area-inset-top))] z-50 flex w-[min(32rem,calc(100vw-1rem))] -translate-x-1/2 flex-col items-center gap-2">
          <div
            role="status"
            className={cn(
              floatingSurfaceElevationClassName,
              "max-w-full rounded-full px-4 py-2 text-sm font-medium",
            )}
          >
            {restartToast}
          </div>
        </div>
      ) : null}
    </>
  );
}
