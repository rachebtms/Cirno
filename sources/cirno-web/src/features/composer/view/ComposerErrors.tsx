import { Alert } from "@heroui/react";
import { PersistenceNotice } from "@/ui/feedback/PersistenceNotice";
import { useComposerView } from "./context";

export function ComposerErrors() {
  const { composerState: state, draftPersistence } = useComposerView();
  const issue = draftPersistence.issue;
  return <>
    {issue && <PersistenceNotice title={state.t(`thread.composer.draftStorage.${issue.action}`)} detail={issue.detail}
      retry={draftPersistence.retry} disabled={state.interactionDisabled} className="composer-error" />}
    {state.queueStorageIssue && <PersistenceNotice
      title={state.t(`thread.composer.queued.${state.queueStorageIssue.action === "read" ? "restoreFailed" : "saveFailed"}`)}
      detail={state.queueStorageIssue.detail} retry={state.queuedPromptStore.retryStorage}
      disabled={state.interactionDisabled} className="composer-error" />}
    {(state.inlineError || state.queueSendError) && <Alert status="danger" role="alert" className="composer-error">
      <Alert.Content>{state.inlineError || state.queueSendError}</Alert.Content>
    </Alert>}
  </>;
}
