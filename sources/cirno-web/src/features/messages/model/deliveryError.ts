import type { MessageDeliveryErrorKind } from "@/lib/contracts/messages";

export function deliveryErrorCopy(
  kind: MessageDeliveryErrorKind | undefined,
  t: (key: string) => string,
): { title: string; body: string } {
  switch (kind) {
    case "message_too_big":
      return {
        title: t("errors.messageTooBig.title"),
        body: t("errors.messageTooBig.body"),
      };
    case "workspace_scope_rejected":
      return {
        title: t("errors.workspaceScopeRejected.title"),
        body: t("errors.workspaceScopeRejected.body"),
      };
    case "turn_rejected":
    case undefined:
      return {
        title: t("errors.turnRejected.title"),
        body: t("errors.turnRejected.body"),
      };
    default: {
      const _exhaustive: never = kind;
      return { title: String(_exhaustive), body: "" };
    }
  }
}
