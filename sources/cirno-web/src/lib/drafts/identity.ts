import type { ComposerDraft } from "./contracts";
export function sameComposerDraft(
  previous: ComposerDraft | undefined,
  draft: ComposerDraft,
): boolean {
  return (
    !!previous &&
    previous.text === draft.text &&
    previous.quotedContext === draft.quotedContext &&
    previous.attachments.length === draft.attachments.length &&
    previous.attachments.every(
      (attachment, index) => attachment === draft.attachments[index],
    ) &&
    previous.sessionMentions.length === draft.sessionMentions.length &&
    previous.sessionMentions.every(
      (mention, index) => mention === draft.sessionMentions[index],
    )
  );
}
