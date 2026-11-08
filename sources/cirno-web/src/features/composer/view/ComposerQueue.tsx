import { Button } from "@heroui/react";
import { CornerDownRight, Paperclip, Pencil, Trash2 } from "lucide-react";
import { queuedPromptLabel, queuedAttachmentLabel } from "../queue/payload";
import { useComposerView } from "./context";

export function ComposerQueue() {
  const { composerState: state, composerSelection: selection, composerMentions: actions } = useComposerView();
  const prompt = state.queuedPrompt;
  if (!prompt) return null;
  const tr = (key: string) => state.t(`thread.composer.queued.${key}`);
  return <aside className="composer-queue" role="group" aria-label={tr("label")}>
    <header><span>{tr("label")}</span>
      <Button type="button" size="sm" variant="ghost" isDisabled={state.interactionDisabled} onPress={() => actions.sendQueuedPrompt(prompt)}><CornerDownRight size={14} />{tr("guide")}</Button>
      <Button type="button" size="sm" isIconOnly variant="ghost" aria-label={tr("edit")}
        isDisabled={state.interactionDisabled || state.encoding || selection.hasErrors} onPress={() => actions.editQueuedPrompt(prompt)}><Pencil size={14} /></Button>
      <Button type="button" size="sm" isIconOnly variant="ghost" aria-label={tr("delete")}
        isDisabled={state.interactionDisabled} onPress={actions.removeQueuedPrompt}><Trash2 size={14} /></Button>
    </header><p>{queuedPromptLabel(prompt, state.t("message.fileAttachment"))}</p>
    {!!prompt.text.trim() && !!prompt.images?.length && <p className="composer-queue-attachments"><Paperclip size={14} aria-hidden />
      <span>{queuedAttachmentLabel(prompt, state.t("message.fileAttachment"))}</span></p>}
  </aside>;
}
