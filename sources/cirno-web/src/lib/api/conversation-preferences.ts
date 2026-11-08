/** Conversation preferences for the versioned Cirno API. */

import type { SidebarStatePayload } from "@/lib/contracts/conversation-preferences";
import { API_READ_TIMEOUT_MS, request } from "./transport";

export async function fetchSidebarState(
  token: string,
  base: string = "",
): Promise<SidebarStatePayload> {
  return request<SidebarStatePayload>(
    `${base}/v0/webui/sidebar-state`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}
