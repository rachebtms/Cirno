import { fetchWithTimeout } from "./http";

export class AccountRequestError extends Error {
  constructor(public code: string) {
    super(code);
    this.name = "AccountRequestError";
  }
}

export async function accountRequest(action: "register" | "login" | "logout" | "complete", values: Record<string, string> = {}): Promise<void> {
  const response = await fetchWithTimeout(`/api/auth/${action}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
  const result = await response.json() as { error?: string };
  if (!response.ok) throw new AccountRequestError(result.error ?? "request_failed");
}
