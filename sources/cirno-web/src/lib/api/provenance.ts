/** History can carry system provenance, a conversation envelope, or both. */
import { isRecord } from "../record";

const origins = new Set(["heartbeat", "scheduled_task", "trigger", "conversation", "subagent", "continuation", "system", "supervision"]);
const optionalString = (value: unknown) => value === undefined || typeof value === "string";

export function isProjectionProvenance(value: unknown): boolean {
  if (!isRecord(value)) return false;
  const source = value.session_message;
  const origin = value.input_origin;
  const validSource = source === undefined || (isRecord(source)
    && typeof source.message_id === "string" && isRecord(source.session));
  const validOrigin = origin === undefined || (isRecord(origin) && typeof origin.kind === "string" && origins.has(origin.kind)
    && [origin.label, origin.id, origin.session_key, origin.conversation_id, origin.received_at, origin.action].every(optionalString)
    && (origin.values === undefined || (isRecord(origin.values)
      && Object.values(origin.values).every(item => typeof item === "string" || typeof item === "number"))));
  return validSource && validOrigin;
}
