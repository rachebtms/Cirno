/** Transport operations for the versioned Cirno API. */

import { fetchWithTimeout } from "../http";

export const API_READ_TIMEOUT_MS = 20_000;

export const API_MUTATION_TIMEOUT_MS = 20_000;

export const PACKAGE_MUTATION_TIMEOUT_MS = 150_000;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export async function responseError(res: Response): Promise<ApiError> {
  const text = typeof res.text === "function" ? (await res.text()).trim() : "";
  let message = text;
  if (text.startsWith("{")) {
    try {
      const payload: unknown = JSON.parse(text);
      if (payload && typeof payload === "object") {
        const error = (payload as { error?: unknown }).error;
        if (typeof error === "string" && error.trim()) message = error.trim();
      }
    } catch {
      // Preserve non-JSON error bodies exactly as returned by the gateway.
    }
  }
  return new ApiError(res.status, message || `HTTP ${res.status}`);
}

export interface WebUIMutationTransport {
  requestMutation<T>(
    action: string,
    payload?: Record<string, unknown>,
    timeoutMs?: number,
  ): Promise<T>;
}

export async function request<T>(
  url: string,
  token: string,
  init?: RequestInit,
  timeoutMs: number = 0,
): Promise<T> {
  const res = await fetchWithTimeout(
    url,
    {
      ...(init ?? {}),
      headers: {
        ...(init?.headers ?? {}),
        Authorization: `Bearer ${token}`,
      },
      credentials: "same-origin",
    },
    timeoutMs,
  );
  if (!res.ok) throw await responseError(res);
  const contentType = res.headers?.get?.("content-type") ?? "";
  if (contentType && !contentType.toLowerCase().includes("application/json")) {
    const text = typeof res.text === "function" ? await res.text() : "";
    const isHtml = text.trimStart().toLowerCase().startsWith("<!doctype");
    throw new ApiError(
      res.status,
      isHtml
        ? "The server returned Web UI HTML instead of JSON. Restart Cirno and try again."
        : "The server returned a non-JSON response.",
    );
  }
  return (await res.json()) as T;
}

export async function mutation<T>(
  transport: WebUIMutationTransport,
  action: string,
  payload: Record<string, unknown> = {},
  timeoutMs: number = API_MUTATION_TIMEOUT_MS,
): Promise<T> {
  try {
    return await transport.requestMutation<T>(action, payload, timeoutMs);
  } catch (reason) {
    const status =
      typeof reason === "object" &&
      reason !== null &&
      "status" in reason &&
      typeof reason.status === "number"
        ? reason.status
        : 500;
    const message =
      reason instanceof Error ? reason.message : "WebUI mutation failed";
    throw new ApiError(status, message);
  }
}
