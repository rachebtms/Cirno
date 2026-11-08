import { isRecord, isRecordArray } from "../record";
/** History operations for the versioned Cirno API. */

import type {
  WebuiThreadPersistedPayload,
  WebuiThreadTraceDetailPayload,
} from "@/lib/contracts/history";
import type { ThreadProjectionEvent } from "@/lib/contracts/events";
import {
  isCompactionPhase,
  isCompactionReason,
} from "../../../packages/client-events/notifications";
import { fetchWithTimeout } from "../http";
import { responseError } from "./transport";

/** Disk-backed WebUI display thread snapshot (separate from agent session). */
export interface FetchWebuiThreadOptions {
  limit?: number;
  direction?: "latest";
  before?: string | null;
  after?: string | null;
  signal?: AbortSignal;
  revision?: string;
  cached?: WebuiThreadPersistedPayload;
}

export function isProjectionMedia(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.url === "string" &&
    (value.name === undefined || typeof value.name === "string") &&
    (value.kind === undefined ||
      ["image", "video", "file"].includes(String(value.kind)))
  );
}

export function hasStringField(
  value: Record<string, unknown>,
  field: string,
): boolean {
  return typeof value[field] === "string";
}

export function isProjectionFileEdit(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStringField(value, "call_id") &&
    hasStringField(value, "tool") &&
    hasStringField(value, "path") &&
    typeof value.added === "number" &&
    typeof value.deleted === "number" &&
    ["editing", "done", "error"].includes(String(value.status))
  );
}

export function hasValidProjectionMetadata(
  value: Record<string, unknown>,
): boolean {
  return (
    (value.projection_id === undefined ||
      typeof value.projection_id === "string") &&
    (value.created_at_ms === undefined ||
      typeof value.created_at_ms === "number") &&
    (value.turn_id === undefined || typeof value.turn_id === "string") &&
    (value.turn_phase === undefined ||
      ["user", "reasoning", "activity", "answer", "complete"].includes(
        String(value.turn_phase),
      )) &&
    (value.turn_seq === undefined || typeof value.turn_seq === "number") &&
    (value.response_sources === undefined ||
      (isRecordArray(value.response_sources) &&
        value.response_sources.every(
          (source) =>
            typeof source.provider === "string" &&
            source.provider.length > 0 &&
            typeof source.model === "string" &&
            source.model.length > 0 &&
            typeof source.preset === "string" &&
            source.preset.length > 0 &&
            (source.fallback === undefined ||
              typeof source.fallback === "boolean"),
        ))) &&
    (value.source === undefined ||
      (isRecord(value.source) &&
        typeof value.source.kind === "string" &&
        (value.source.label === undefined ||
          typeof value.source.label === "string")))
  );
}

export function isProjectionTraceDetail(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.ref === "string" &&
    /^\d{1,12}\.\d{1,12}\.\d{1,12}\.[0-9a-f]{20}\.history-[0-9a-f]{20}$/.test(
      value.ref,
    ) &&
    typeof value.bytes === "number" &&
    Number.isFinite(value.bytes) &&
    value.bytes >= 0 &&
    typeof value.traceCount === "number" &&
    Number.isInteger(value.traceCount) &&
    value.traceCount >= 0
  );
}

export function parseThreadProjectionEvent(
  value: unknown,
): ThreadProjectionEvent {
  if (
    !isRecord(value) ||
    typeof value.event !== "string" ||
    typeof value.chat_id !== "string"
  ) {
    throw new Error("Invalid WebUI thread event");
  }
  if (
    !hasValidProjectionMetadata(value) ||
    (value.stream_id !== undefined && typeof value.stream_id !== "string") ||
    (value.projection_receipts !== undefined &&
      (!Array.isArray(value.projection_receipts) ||
        !value.projection_receipts.every(
          (receipt: unknown) =>
            isRecord(receipt) &&
            typeof receipt.turn_id === "string" &&
            receipt.turn_id.length > 0 &&
            Array.isArray(receipt.ranges) &&
            receipt.ranges.every(
              (range: unknown) =>
                Array.isArray(range) &&
                range.length === 2 &&
                Number.isSafeInteger(range[0]) &&
                range[0] >= 0 &&
                Number.isSafeInteger(range[1]) &&
                range[1] >= range[0],
            ),
        )))
  ) {
    throw new Error("Invalid WebUI thread event metadata");
  }
  switch (value.event) {
    case "user_message":
      if (
        typeof value.text !== "string" ||
        typeof value.starts_turn !== "boolean"
      )
        break;
      if (
        value.media_urls !== undefined &&
        (!Array.isArray(value.media_urls) ||
          !value.media_urls.every(isProjectionMedia))
      )
        break;
      if (
        value.cli_apps !== undefined &&
        (!isRecordArray(value.cli_apps) ||
          !value.cli_apps.every((item) => hasStringField(item, "name")))
      )
        break;
      if (
        value.mcp_presets !== undefined &&
        (!isRecordArray(value.mcp_presets) ||
          !value.mcp_presets.every((item) => hasStringField(item, "name")))
      )
        break;
      if (
        value.session_mentions !== undefined &&
        (!isRecordArray(value.session_mentions) ||
          !value.session_mentions.every(
            (item) =>
              hasStringField(item, "name") &&
              hasStringField(item, "session_key") &&
              hasStringField(item, "title"),
          ))
      )
        break;
      if (
        value.provenance !== undefined &&
        (!isRecord(value.provenance) ||
          !isRecord(value.provenance.session_message) ||
          !hasStringField(value.provenance.session_message, "message_id") ||
          !isRecord(value.provenance.session_message.session))
      )
        break;
      return value as unknown as ThreadProjectionEvent;
    case "message":
      if (typeof value.text !== "string") break;
      if (value.tool_events !== undefined && !isRecordArray(value.tool_events))
        break;
      if (
        value.trace_detail !== undefined &&
        (!["tool_hint", "progress"].includes(String(value.kind)) ||
          !isProjectionTraceDetail(value.trace_detail))
      )
        break;
      if (
        value.media_urls !== undefined &&
        (!Array.isArray(value.media_urls) ||
          !value.media_urls.every(isProjectionMedia))
      )
        break;
      return value as unknown as ThreadProjectionEvent;
    case "file_edit":
      if (
        !Array.isArray(value.edits) ||
        !value.edits.every(isProjectionFileEdit)
      )
        break;
      return value as unknown as ThreadProjectionEvent;
    case "delta":
    case "reasoning_delta":
      if (typeof value.text !== "string") break;
      return value as unknown as ThreadProjectionEvent;
    case "stream_end":
    case "reasoning_end":
      if (value.text !== undefined && typeof value.text !== "string") break;
      return value as unknown as ThreadProjectionEvent;
    case "context_compaction":
      if (
        typeof value.compaction_id !== "string" ||
        !value.compaction_id ||
        !isCompactionPhase(value.phase) ||
        (value.reason !== undefined && !isCompactionReason(value.reason))
      )
        break;
      return value as unknown as ThreadProjectionEvent;
    case "turn_end":
      return value as unknown as ThreadProjectionEvent;
  }
  throw new Error(`Invalid WebUI thread projection event: ${value.event}`);
}

export function parseWebuiThreadPayload(
  value: unknown,
): WebuiThreadPersistedPayload {
  if (!isRecord(value) || typeof value.schemaVersion !== "number") {
    throw new Error("Invalid WebUI thread response");
  }
  if (value.projection !== "events" || !Array.isArray(value.events)) {
    throw new Error("Invalid WebUI thread events");
  }
  const events = value.events.map(parseThreadProjectionEvent);
  return {
    ...value,
    projection: "events",
    events,
  } as unknown as WebuiThreadPersistedPayload;
}

export function parseWebuiThreadTraceDetailPayload(
  value: unknown,
): WebuiThreadTraceDetailPayload {
  if (
    !isRecord(value) ||
    typeof value.message_id !== "string" ||
    !/^history-[0-9a-f]{20}$/.test(value.message_id) ||
    !Array.isArray(value.events)
  ) {
    throw new Error("Invalid WebUI thread trace detail response");
  }
  return {
    message_id: value.message_id,
    events: value.events.map(parseThreadProjectionEvent),
  };
}

export async function fetchWebuiThread(
  token: string,
  key: string,
  optionsOrBase?: FetchWebuiThreadOptions | string,
  base: string = "",
): Promise<WebuiThreadPersistedPayload | null> {
  const options = typeof optionsOrBase === "string" ? undefined : optionsOrBase;
  const resolvedBase = typeof optionsOrBase === "string" ? optionsOrBase : base;
  const params = new URLSearchParams();
  if (options?.limit !== undefined) params.set("limit", String(options.limit));
  if (options?.direction) params.set("direction", options.direction);
  if (options?.before) params.set("before", options.before);
  if (options?.after) params.set("after", options.after);
  const query = params.toString();
  const suffix = query ? `?${query}` : "";
  const url = `${resolvedBase}/v0/sessions/${encodeURIComponent(key)}/webui-thread${suffix}`;
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (options?.revision) headers["If-None-Match"] = `"${options.revision}"`;
  const res = await fetchWithTimeout(url, {
    headers,
    credentials: "same-origin",
    cache: "no-store",
    signal: options?.signal,
  });
  if (res.status === 304 && options?.cached) return options.cached;
  if (res.status === 404) return null;
  if (!res.ok) throw await responseError(res);
  return parseWebuiThreadPayload(await res.json());
}

export async function fetchWebuiThreadTraceDetail(
  token: string,
  key: string,
  ref: string,
  base: string = "",
): Promise<WebuiThreadTraceDetailPayload> {
  const query = new URLSearchParams({ ref });
  const url = `${base}/v0/sessions/${encodeURIComponent(key)}/webui-thread/trace-detail?${query}`;
  const res = await fetchWithTimeout(url, {
    headers: { Authorization: `Bearer ${token}` },
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!res.ok) throw await responseError(res);
  return parseWebuiThreadTraceDetailPayload(await res.json());
}
