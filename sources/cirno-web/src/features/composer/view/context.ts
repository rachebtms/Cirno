import type { useDraftPersistence } from "../useDraftPersistence";
import { createContext, useContext } from "react";
import type { ComponentInputs } from "../inputs";
import type { useComposerActions } from "../useComposerActions";
import type { useComposerAttachments } from "../useComposerAttachments";
import type { useComposerCommands } from "../useComposerCommands";
import type { useComposerDelivery } from "../useComposerDelivery";
import type { useComposerKeyboard } from "../useComposerKeyboard";
import type { useComposerMentions } from "../useComposerMentions";
import type { useComposerQueues } from "../useComposerQueues";
import type { useComposerSelection } from "../useComposerSelection";
import type { useComposerState } from "../useComposerState";

export interface ComposerViewModel {
  draftPersistence: ReturnType<typeof useDraftPersistence>;
  inputs: ComponentInputs;
  composerState: ReturnType<typeof useComposerState>;
  composerActions: ReturnType<typeof useComposerActions>;
  composerAttachments: ReturnType<typeof useComposerAttachments>;
  composerCommands: ReturnType<typeof useComposerCommands>;
  composerDelivery: ReturnType<typeof useComposerDelivery>;
  composerKeyboard: ReturnType<typeof useComposerKeyboard>;
  composerMentions: ReturnType<typeof useComposerMentions>;
  composerQueues: ReturnType<typeof useComposerQueues>;
  composerSelection: ReturnType<typeof useComposerSelection>;
}
export const ComposerViewContext = createContext<ComposerViewModel | null>(null);
export function useComposerView() {
  const model = useContext(ComposerViewContext);
  if (!model) throw new Error("Composer view requires its controller");
  return model;
}
