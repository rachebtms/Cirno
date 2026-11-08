/** Canonical projection shared by live events and persisted transcript replay. */
export type { ThreadProjectionEvent } from "@/lib/contracts/events";
export type {
  UIMessageTurnFields,
  ThreadProjectionState,
  ThreadProjectionEffects,
  ThreadProjectionOptions,
} from "./contracts";
export { turnFieldsFromEvent, finalizeStreamedTurn } from "./turns";
export {
  createThreadProjectionState,
  resetThreadProjectionCursor,
  clearThreadProjectionActivity,
  closeThreadProjectionAnswer,
} from "./state";
export { projectThreadEvent, projectThreadEvents } from "./reducer";
export { appendProjectedSessionInput, transitionTurnDelivery } from "./inputs";
