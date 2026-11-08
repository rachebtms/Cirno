import { toast } from "@heroui/react";
import i18n from "@/i18n";
import type { CirnoClient } from "@/lib/cirno-client";
import type { ProviderOAuthAuthorizationRequired } from "@/lib/contracts/models";
import { cancelAuthorization } from "./cancelAuthorization";

/** Cleanup still has a visible failure path after its editor has gone away. */
export async function releaseAuthorization(
  client: CirnoClient,
  flow: ProviderOAuthAuthorizationRequired,
) {
  try {
    await cancelAuthorization(client, flow);
  } catch (reason) {
    reportAuthorizationReleaseError(client, flow, reason);
  }
}

export function reportAuthorizationReleaseError(
  client: CirnoClient,
  flow: ProviderOAuthAuthorizationRequired,
  reason: unknown,
) {
  const title = i18n.t("settings.oauth.cancelFailed", { provider: flow.provider });
  const show = (error: unknown) => ({
    description: error instanceof Error ? error.message : String(error),
    timeout: 0,
    actionProps: { children: i18n.t("common.retry"), onPress: retry },
  });
  async function retry() {
    toast.update(id, title, {
      isLoading: true,
      actionProps: { children: i18n.t("common.retry"), isDisabled: true },
    });
    try {
      await cancelAuthorization(client, flow);
      toast.close(id);
    } catch (error) {
      toast.update(id, title, { ...show(error), isLoading: false });
    }
  }
  const id = toast.danger(title, show(reason));
}
