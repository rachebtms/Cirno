/** Bounded prompt-directory pages; search runs against the same server projection. */
import type { PromptPage } from "../contracts/history";
import { fetchWithTimeout } from "../http";
import { responseError } from "./transport";
import { isRecord } from "../record";

export const PROMPT_PAGE_SIZE = 64;
export interface PromptPageOptions { offset?: number; limit?: number; query?: string }

export async function fetchPromptPage(
  token: string, key: string, signal: AbortSignal, options: PromptPageOptions = {},
): Promise<PromptPage> {
  const params = new URLSearchParams({ limit: String(options.limit ?? PROMPT_PAGE_SIZE) });
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  if (options.query) params.set("q", options.query);
  const response = await fetchWithTimeout(`/v0/sessions/${encodeURIComponent(key)}/webui-thread/prompts?${params}`, {
    headers: { Authorization: `Bearer ${token}` }, credentials: "same-origin", cache: "no-store", signal,
  });
  if (!response.ok) throw await responseError(response);
  const body: unknown = await response.json();
  if (!isRecord(body) || !Array.isArray(body.prompts)
    || !Number.isSafeInteger(body.offset) || Number(body.offset) < 0
    || !Number.isSafeInteger(body.total) || Number(body.total) < Number(body.offset)
    || !Number.isSafeInteger(body.count) || Number(body.count) < Number(body.total)
    || body.prompts.length > (options.limit ?? PROMPT_PAGE_SIZE)
    || Number(body.offset) + body.prompts.length > Number(body.total)
    || (body.revision !== null && typeof body.revision !== "string")) {
    throw new Error("Invalid prompt directory page");
  }
  let previous = -1;
  const prompts = body.prompts.map((item: unknown) => {
    if (!isRecord(item) || typeof item.id !== "string" || !item.id
      || typeof item.preview !== "string" || typeof item.answerPreview !== "string"
      || typeof item.cursor !== "string" || typeof item.turnId !== "string"
      || typeof item.createdAt !== "number" || !Number.isFinite(item.createdAt)
      || !Number.isSafeInteger(item.index) || Number(item.index) <= previous
      || Number(item.index) >= Number(body.count)) throw new Error("Invalid prompt summary");
    previous = Number(item.index);
    return { id: item.id, preview: item.preview, answerPreview: item.answerPreview,
      cursor: item.cursor, turnId: item.turnId, createdAt: item.createdAt, index: previous };
  });
  return { prompts, offset: Number(body.offset), total: Number(body.total), count: Number(body.count),
    revision: body.revision as string | null };
}
