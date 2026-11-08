import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useLifetime } from "@/ui/resources/useLifetime";
import type { ComponentInputs } from "./inputs";
import type { useComposerState } from "./useComposerState";
import type { useComposerAttachments } from "./useComposerAttachments";

export function useDraftPersistence(inputs: ComponentInputs, state: ReturnType<typeof useComposerState>,
  attachments: ReturnType<typeof useComposerAttachments>) {
  const { draftStore: store, draftKey: key } = inputs;
  const owner = useMemo(() => ({ store, key }), [store, key]);
  const current = useLifetime(owner);
  const subscribe = useCallback((listener: () => void) => key && store
    ? store.subscribeStorage(key, listener) : () => {}, [store, key]);
  const snapshot = useCallback(() => key ? store?.getStorageIssue(key) ?? null : null, [store, key]);
  const issue = useSyncExternalStore(subscribe, snapshot);
  const retry = () => {
    if (!current() || !store || !key) return;
    const draft = store.retryStorage(key);
    if (!draft) return;
    attachments.replaceMentionInput(draft.text, draft.text.length);
    state.setBoundSessionMentions(draft.sessionMentions);
    state.clear();
    state.restoreDraftAttachments(draft.attachments);
    inputs.onQuotedContextChange?.(draft.quotedContext);
  };
  return { issue, retry };
}
