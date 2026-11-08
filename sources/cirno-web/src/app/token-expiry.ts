import { TOKEN_REFRESH_MARGIN_MS, TOKEN_REFRESH_MIN_DELAY_MS } from "./navigation";

export function bootstrapTokenExpiresAt(expiresInSeconds: number): number {
  return Date.now() + Math.max(0, expiresInSeconds) * 1000;
}

export function tokenRefreshDelayMs(expiresAt: number): number {
  const remaining = Math.max(0, expiresAt - Date.now());
  const margin = Math.min(
    TOKEN_REFRESH_MARGIN_MS,
    Math.max(1_000, remaining / 2),
  );
  return Math.max(TOKEN_REFRESH_MIN_DELAY_MS, remaining - margin);
}
