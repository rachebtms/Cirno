import type { ComposerDraft } from "./contracts";
const acceptedDraftListeners = new WeakMap<
  Map<string, ComposerDraft>,
  Set<(key: string) => void>
>();

export function onComposerDraftAccepted(
  store: Map<string, ComposerDraft>,
  listener: (key: string) => void,
): () => void {
  const listeners = acceptedDraftListeners.get(store) ?? new Set();
  acceptedDraftListeners.set(store, listeners);
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Clear only the submitted revision, including a composer remounted while awaiting its receipt. */
export function acceptComposerDraft(
  store: Map<string, ComposerDraft>,
  key: string,
  submitted: ComposerDraft | undefined,
): boolean {
  if (store.get(key) !== submitted) return false;
  store.delete(key);
  for (const listener of acceptedDraftListeners.get(store) ?? []) listener(key);
  return true;
}
