import { Button } from "@heroui/react";
import { Hint } from "@/ui/feedback/Hint";
import { Paperclip, Terminal } from "lucide-react";
import { ComposerActionIcon } from "@/components/thread/ComposerActionIcon";
import { ACCEPT_ATTR } from "@/hooks/useAttachedImages";
import { useComposerView } from "./context";

export function ComposerToolbar() {
  const { inputs, composerState: state, composerActions: actions, composerSelection: selection,
    composerKeyboard: keyboard, composerMentions: mentions, composerCommands: commands } = useComposerView();
  const label = mentions.showContinueButton ? state.t("recovery.continue")
    : keyboard.showStopButton ? state.t("thread.composer.stop")
    : selection.requiresModelSetup ? state.t("thread.composer.configureModel")
    : state.t(selection.isUserShell ? "thread.composer.shell.run" : "thread.composer.send");
  const buttonDisabled = keyboard.showStopButton || mentions.showContinueButton
    ? state.interactionDisabled : !selection.canSend && !selection.canOpenModelSettings;
  return <footer className="thread-composer-footer composer-toolbar">
    <div className="thread-composer-footer-primary composer-toolbar-start">
      <input ref={state.fileInputRef} type="file" multiple accept={ACCEPT_ATTR} hidden onChange={keyboard.onFilePick} />
      <Hint content={state.t("thread.composer.attachImage")}><Button type="button" isIconOnly variant="ghost" aria-label={state.t("thread.composer.attachImage")}
        isDisabled={keyboard.attachButtonDisabled} onPress={() => state.fileInputRef.current?.click()} className="composer-icon-action">
        <Paperclip size={18} aria-hidden />
      </Button></Hint>
      {!state.mobileWorkspaceControls && keyboard.accessControl}
    </div>
    <div className="thread-composer-footer-actions composer-toolbar-end">
      {actions.modelControl}{!actions.usageInMeta && actions.usageControl}
      <Hint content={label}><Button type={keyboard.showStopButton || selection.requiresModelSetup ? "button" : "submit"} isIconOnly
        variant={keyboard.showStopButton ? "secondary" : "primary"} className="composer-primary-action composer-icon-action"
        aria-label={label} isDisabled={buttonDisabled}
        onPress={keyboard.showStopButton ? commands.handleStop : selection.requiresModelSetup ? inputs.onModelBadgeClick : undefined}>
        {selection.isUserShell && keyboard.actionState === "send" ? <Terminal size={18} aria-hidden /> : <ComposerActionIcon state={keyboard.actionState} />}
      </Button></Hint>
    </div>
  </footer>;
}

export function ComposerMetadata() {
  const { composerState: state, composerActions: actions, composerKeyboard: keyboard } = useComposerView();
  const usage = actions.usageInMeta ? actions.usageControl : null;
  const access = state.mobileWorkspaceControls ? keyboard.accessControl : null;
  if (!keyboard.workspaceControl && !usage && !access) return null;
  return <div className="thread-composer-meta composer-metadata">
    <div className="thread-composer-workspace-group composer-workspace">{keyboard.workspaceControl}</div>
    {(usage || access) && <div className="composer-metadata-actions">{usage}{access}</div>}
  </div>;
}
