import { ModelsIcon } from "@/components/icons/product-icons";
import { LoadingRing } from "@/components/ui/loading-ring";

export type ComposerActionState = "busy" | "stop" | "setup" | "send";

export function ComposerActionIcon({ state }: { state: ComposerActionState }) {
  return (
    <span className="composer-action-icons pointer-events-none relative block h-7 w-7 shrink-0" data-state={state} aria-hidden="true">
      <span className="composer-action-glyph" data-action-icon="send" data-active={state === "send" || undefined}>
        <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="m8.25 10.25 3.75-3.75 3.75 3.75M12 7v10.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span className="composer-action-glyph" data-action-icon="stop" data-active={state === "stop" || undefined}>
        <LoadingRing track={false} strokeDasharray="12 50.8" className="absolute h-6 w-6 text-foreground/50" strokeWidth="1.5" />
        <svg className="h-6 w-6" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <rect x="8" y="8" width="8" height="8" rx="1.75" />
        </svg>
      </span>
      <span className="composer-action-glyph" data-action-icon="busy" data-active={state === "busy" || undefined}>
        <LoadingRing className="h-4 w-4" />
      </span>
      <span className="composer-action-glyph" data-action-icon="setup" data-active={state === "setup" || undefined}>
        <ModelsIcon className="h-4 w-4" />
      </span>
    </span>
  );
}
