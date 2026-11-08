import { ComposerErrors } from "./ComposerErrors";
import { hasDraggedSession } from "@/lib/session-drag";
import { CliAppMentionPalette } from "../MentionPalette";
import { SlashCommandPalette } from "../SlashPalette";
import { ComposerAttachments } from "./ComposerAttachments";
import { ComposerEditor } from "./ComposerEditor";
import { ComposerQueue } from "./ComposerQueue";
import { ComposerMetadata, ComposerToolbar } from "./ComposerToolbar";
import { ComposerGoal } from "./ComposerGoal";
import { ComposerViewContext, type ComposerViewModel } from "./context";
import "./composer.css";

export function ComposerView(model: ComposerViewModel) {
  const { inputs, composerState: state, composerSelection: selection, composerActions: actions,
    composerQueues: queues, composerCommands: commands, composerDelivery: delivery } = model;
  return <ComposerViewContext value={model}>
    <form ref={state.formRef} className="thread-composer-form composer-form" data-palette-beside={actions.paletteBeside || undefined}
      data-compact-controls={state.compactControls || undefined}
      onSubmit={event => { event.preventDefault(); delivery.submit(); }}
      onDragEnter={event => { if (!commands.previewSessionDrop(event)) state.onDragEnter(event); }}
      onDragOver={event => { if (!commands.previewSessionDrop(event)) state.onDragOver(event); }}
      onDragLeave={event => {
        if (!hasDraggedSession(event.dataTransfer)) { state.onDragLeave(event); return; }
        if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) state.setSessionDragPreview(null);
      }} onDrop={event => { if (!commands.handleSessionDrop(event)) state.onDrop(event); }}>
      {selection.showSlashMenu && <SlashCommandPalette commands={selection.filteredSlashCommands} selectedIndex={state.selectedCommandIndex}
        layout={queues.slashPaletteLayout} isHero={state.isHero} onHover={state.setSelectedCommandIndex} onChoose={commands.chooseSlashCommand} />}
      {queues.showCliAppMenu && <CliAppMentionPalette candidates={queues.filteredMentionCandidates} selectedIndex={state.selectedCliAppIndex}
        layout={queues.slashPaletteLayout} isHero={state.isHero} onHover={state.setSelectedCliAppIndex} onChoose={commands.chooseMentionCandidate} />}
      <div className="thread-composer-surface composer-surface" ref={inputs.surfaceRef}
        data-dragging={state.isDragging || Boolean(state.sessionDragPreview) || undefined}
        data-disabled={state.interactionDisabled || undefined}
        style={actions.paletteBeside ? { maxHeight: queues.slashPaletteLayout.maxHeight, overflowY: "auto" } : undefined}>
        <ComposerQueue /><ComposerAttachments /><ComposerGoal /><ComposerEditor />
        <ComposerErrors />
        <ComposerToolbar />
      </div>
      <ComposerMetadata />
    </form>
  </ComposerViewContext>;
}
