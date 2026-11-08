import type { UIMessage } from "@/lib/contracts/messages";

export type UIMessageTurnFields = Pick<UIMessage, "turnId" | "turnPhase" | "turnSeq">;

export interface ThreadProjectionState {
  messages: UIMessage[];
  activeAssistantId: string | null;
  closedAssistantIds: Set<string>;
  /** Completed wire identities also fence late deltas for textless ends. */
  closedAnswerStreamIds: Set<string>;
  mergeReasoning: boolean;
  activitySegmentId: string | null;
  fileEditSegmentId: string | null;
  activitySegmentCounter: number;
  suppressUntilTurnEnd: boolean;
  closedTurnIds: Set<string>;
  turnAliases: Map<string, string>;
}

export interface ThreadProjectionEffects {
  /** Content targets, including cleaned trace rows removed by this event. */
  bodyWrites: Set<string>;
  /** Absorbed/replaced rows; an absorbed ID can also remain a body target. */
  consumed: Set<string>;
}

export interface ThreadProjectionOptions {
  createId: () => string;
  now: number;
  persisted?: boolean;
  sideChannel?: boolean;
  /** First sequence of a coalesced batch; event.turn_seq is its last contribution. */
  startSeq?: number;
  effects?: ThreadProjectionEffects;
}
