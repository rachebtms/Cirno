
import { ShellSurface } from "./ShellSurface";
import { useConversationActions } from "./useConversationActions";
import { useConversationLifecycle } from "./useConversationLifecycle";
import { useConversationProjection } from "./useConversationProjection";
import { useConversationState } from "./useConversationState";
import { useNavigationActions } from "./useNavigationActions";
import { useRuntimeActions } from "./useRuntimeActions";
import { useWorkspaceActions } from "./useWorkspaceActions";
import { useWorkspacePresentation } from "./useWorkspacePresentation";
import { useWorkspaceState } from "./useWorkspaceState";
export function Shell({

  onModelNameChange,
  onLogout,

}: {

  onModelNameChange: (modelName: string | null) => void;
  onLogout: () => void;

}) {
  const inputs = {

    onModelNameChange,
    onLogout,

  };
  const workspaceState = useWorkspaceState();
  const conversationProjection = useConversationProjection({ workspaceState });
  const conversationState = useConversationState({ workspaceState });
  const conversationLifecycle = useConversationLifecycle({
    workspaceState,
    conversationState,
    conversationProjection,
  });
  const workspaceActions = useWorkspaceActions({
    conversationProjection,
    workspaceState,
    conversationState,
  });
  const conversationActions = useConversationActions({
    workspaceState,
    conversationProjection,
    workspaceActions,
  });
  const runtimeActions = useRuntimeActions({
    workspaceState,
    conversationProjection,
    conversationState,
    inputs,
  });
  const navigationActions = useNavigationActions({ workspaceState });
  const workspacePresentation = useWorkspacePresentation({
    workspaceState,
    conversationState,
    workspaceActions,
    navigationActions,
    conversationActions,
  });
  return (
    <ShellSurface
      workspaceState={workspaceState}
      workspacePresentation={workspacePresentation}
      conversationLifecycle={conversationLifecycle}
      conversationActions={conversationActions}
      conversationState={conversationState}
      conversationProjection={conversationProjection}
      workspaceActions={workspaceActions}
      runtimeActions={runtimeActions}
      inputs={inputs}
      navigationActions={navigationActions}
    />
  );
}
