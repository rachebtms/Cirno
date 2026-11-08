import { fetchWithTimeout } from "./http";

export class AccountRequestError extends Error {
  constructor(public code: string) {
    super(code);
    this.name = "AccountRequestError";
  }
}

export async function accountRequest<T = void>(action: "register" | "login" | "logout" | "complete" | "change-password" | "change-router-name", values: Record<string, string> = {}): Promise<T> {
  const response = await fetchWithTimeout(`/v0/auth/${action}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
  const result = await response.json() as { error?: string };
  if (!response.ok) throw new AccountRequestError(result.error ?? "request_failed");
  return result as T;
}

export type AccountStatus = { enabled: boolean; authenticated: boolean; registration_required: boolean; username: string | null; router_handle?: string | null; router_id?: string };

export async function accountStatus(): Promise<AccountStatus> {
  const response = await fetchWithTimeout("/v0/auth/status", { credentials: "same-origin" });
  const result = await response.json() as AccountStatus & { error?: string };
  if (!response.ok) throw new AccountRequestError(result.error ?? "request_failed");
  return result;
}

export function validAccountPassword(password: string): boolean {
  return Array.from(password).length >= 10 && /\p{Lu}/u.test(password) && /[\p{P}\p{S}]/u.test(password);
}
