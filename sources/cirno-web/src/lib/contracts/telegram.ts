/** Private Telegram pairing and notification preferences. PIN times are Unix milliseconds. */
export type TelegramNotification = "router" | "operations" | "conversations" | "system";
export interface TelegramBinding {
  bound: boolean;
  enabled: boolean;
  username?: string;
  user_id?: string;
  notifications: TelegramNotification[];
  webui_url: string;
}
export interface TelegramPin {
  pin: string;
  expires_at: number;
  ttl_seconds: number;
}
export type TelegramPreferences = Partial<Pick<TelegramBinding, "enabled" | "notifications" | "webui_url">>;
