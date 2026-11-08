import { Button, TextArea } from "@heroui/react";
import { Quote, X } from "lucide-react";
import { ComposerInlineReferenceOverlay } from "../InlineGuidance";
import { useComposerView } from "./context";

export function ComposerEditor() {
  const { inputs, composerState: state, composerAttachments: attachments, composerSelection: selection,
    composerQueues: queues, composerKeyboard: keyboard } = useComposerView();
  const { mentionInput } = attachments;
  const updateCursor = () => state.setCursorPosition(attachments.rawSelection().start);
  return <>
    {selection.normalizedQuotedContext && <aside className="composer-quote" aria-label={state.t("thread.composer.quotedContext")}>
      <Quote size={16} aria-hidden /><p>{selection.normalizedQuotedContext}</p>
      <Button isIconOnly variant="ghost" size="sm" aria-label={state.t("thread.composer.removeQuotedContext")}
        onPress={() => { inputs.onQuotedContextChange?.(null); requestAnimationFrame(() => state.textareaRef.current?.focus()); }}><X size={16} /></Button>
    </aside>}
    <div className="thread-composer-input composer-editor">
      {queues.hasInlineDecorations && <ComposerInlineReferenceOverlay overlayRef={state.mentionOverlayRef}
        segments={queues.inlineSegments} slashCommand={queues.slashCommand?.command ?? null} isHero={state.isHero}
        isComposing={mentionInput.isComposing} className="composer-editor-text"
        ghostRange={attachments.sessionDragInsertion ? { start: attachments.sessionDragInsertion.tokenStart, end: attachments.sessionDragInsertion.tokenEnd } : null} />}
      <TextArea ref={state.textareaRef} value={mentionInput.value} rows={1}
        className={`composer-editor-text ${queues.hasInlineDecorations ? "composer-editor-decorated" : ""}`}
        aria-label={inputs.inputAriaLabel ?? state.t("thread.composer.inputAria")}
        placeholder={state.sessionDragPreview ? "" : state.resolvedPlaceholder} disabled={state.interactionDisabled}
        enterKeyHint={state.hasCoarsePointer ? "enter" : undefined}
        onChange={mentionInput.onChange} onCompositionStart={mentionInput.onCompositionStart} onCompositionEnd={mentionInput.onCompositionEnd}
        onKeyDown={keyboard.onKeyDown} onKeyUp={updateCursor} onSelect={updateCursor} onClick={updateCursor}
        onCopy={mentionInput.onCopy} onCut={mentionInput.onCut} onPaste={attachments.onPaste}
        onScroll={event => { if (state.mentionOverlayRef.current) state.mentionOverlayRef.current.scrollTop = event.currentTarget.scrollTop; }} />
    </div>
  </>;
}
