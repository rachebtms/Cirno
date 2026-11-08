/** JSON object guards shared by transport, persistence and projection readers. */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function isRecordArray(value: unknown): value is Array<Record<string, unknown>> {
  return Array.isArray(value) && value.every(isRecord);
}
