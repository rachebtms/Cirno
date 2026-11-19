import type { InboundEvent } from "./contracts/events";
import type { RunObservation } from "./client-run-ledger";

export const SYSTEM_COMMAND_TURN_PREFIX = "webui-system:";

export function isSystemCommandTurnId(value: string | null | undefined): value is string {
  return typeof value === "string" && value.startsWith(SYSTEM_COMMAND_TURN_PREFIX);
}
export function runObservation(event: InboundEvent): RunObservation | null {
  if (!("chat_id" in event) || !event.chat_id) return null;
  const turnId = "turn_id" in event && typeof event.turn_id === "string" ? event.turn_id : null;
  const base = { chatId: event.chat_id, turnId, systemCommand: isSystemCommandTurnId(turnId) };
  switch (event.event) {
    case "message_accepted":
    case "user_message": {
      const activeTurnId = event.active_turn_id ?? (event.starts_turn ? event.turn_id : undefined);
      // Receiving a Router note is input, not evidence of executing it.
      // Only explicit admission ownership or actual run activity starts work.
      return {
        ...base,
        kind: event.event === "message_accepted" ? "admission" : "input",
        ...(activeTurnId ? { owner: { turnId: activeTurnId, startedAt: event.started_at } } : {}),
      };
    }
    case "goal_status":
      return { ...base, kind: "status", activity: event.status, startedAt: event.started_at };
    case "turn_end":
      return { ...base, kind: "completed" };
    case "error":
      return { ...base, kind: "rejection" };
    case "delta":
    case "reasoning_delta":
      return { ...base, kind: event.text ? "activity" : "progress" };
    case "stream_end":
      return { ...base, kind: "activity" };
    case "retry_status":
      return { ...base, kind: event.state === "recovered" || event.state === "cleared" ? "progress" : "activity" };
    case "recovery_state":
      // Supersession resolves the old recovery, not the new user turn that caused it.
      return event.status === "recovered" && event.reason === "superseded"
        ? { ...base, kind: "progress" }
        : { ...base, kind: "recovery", active: event.status === "resuming" };
    case "attached":
      return event.recovery_state && event.recovery_state.status !== "recovered"
        ? { ...base, kind: "recovery", active: event.recovery_state.status === "resuming" }
        : { ...base, kind: "progress" };
    case "message":
      return { ...base, kind: "message" };
    default:
      return { ...base, kind: "progress" };
  }
}
