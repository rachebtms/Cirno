import type { McpOAuthFlowPayload } from "@/lib/contracts/mcp";
export function mcpOAuthStatusText(
  status: McpOAuthFlowPayload["status"],
  popupBlocked: boolean,
  tx: (key: string, fallback: string) => string,
  completionInput?: McpOAuthFlowPayload["completion_input"],
): string {
  switch (status) {
    case "starting":
      return tx("settings.mcp.preparingSignIn", "Preparing secure sign-in...");
    case "authorization_required":
      if (completionInput === "callback_url") {
        return tx(
          "settings.mcp.manualCallbackRequired",
          "Finish signing in, then paste the callback URL into cirno.",
        );
      }
      return popupBlocked
        ? tx("settings.mcp.openSignInToContinue", "Open the sign-in page to continue.")
        : tx("settings.mcp.finishSignInInBrowser", "Complete sign-in in the browser window.");
    case "connecting":
      return tx("settings.mcp.finishingConnection", "Finishing connection...");
    case "authorized":
      return tx("settings.mcp.activatingTools", "Activating tools...");
    case "connected":
      return tx("settings.mcp.connected", "Connected.");
    case "failed":
      return tx("settings.mcp.connectionFailed", "Connection failed.");
    case "cancelled":
      return tx("settings.mcp.connectionCancelled", "Connection cancelled.");
  }
}

export function mcpPresetStatusLabel(
  status: string,
  tx: (key: string, fallback: string) => string,
): string {
  switch (status) {
    case "configured":
      return tx("settings.mcp.statusConfigured", "Configured");
    case "missing_credentials":
      return tx("settings.mcp.statusMissingCredentials", "Needs key");
    case "missing_dependency":
      return tx("settings.mcp.statusMissingDependency", "Needs dependency");
    case "coming_soon":
      return tx("settings.mcp.statusComingSoon", "Coming soon");
    default:
      return tx("settings.mcp.statusNotInstalled", "Not enabled");
  }
}
