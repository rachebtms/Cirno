import { ApiError, cancelProviderOAuth } from "@/lib/api";
import type { CirnoClient } from "@/lib/cirno-client";
import type { ProviderOAuthAuthorizationRequired } from "@/lib/contracts/models";

export async function cancelAuthorization(
  client: CirnoClient,
  flow: ProviderOAuthAuthorizationRequired,
) {
  try {
    await cancelProviderOAuth(client, flow.provider, flow.flow_id);
  } catch (reason) {
    // An expired or completed flow has no server resource left to cancel.
    if (!(reason instanceof ApiError && reason.status === 410)) throw reason;
  }
}
