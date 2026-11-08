import { expireQueuedPromptAuthorization } from "@/features/composer/queue/store";
import { toast } from "@heroui/react";
import i18n from "@/i18n";
import { clearStoredComposerDrafts } from "@/lib/composer-draft";

/** Account transitions still complete when browser storage denies cleanup. */
export function clearBrowserDrafts() {
  expireQueuedPromptAuthorization();
  try { clearStoredComposerDrafts(); }
  catch (error) {
    toast.danger(i18n.t("thread.composer.draftStorage.clearFailed"), {
      description: error instanceof Error ? error.message : String(error), timeout: 0,
    });
  }
}
