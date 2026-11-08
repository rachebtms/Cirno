/** Browser API: public operations grouped by domain. */

export { ApiError } from "./transport";
export type { WebUIMutationTransport } from "./transport";
export { listSessions, deleteSession } from "./sessions";
export {
  parseWebuiThreadPayload,
  fetchWebuiThread,
  fetchWebuiThreadTraceDetail,
} from "./history";
export type { FetchWebuiThreadOptions } from "./history";
export {
  fetchFilePreview,
  fetchFileReferenceMetadata,
  fetchFilePreviewAvailability,
} from "./files";
export {
  fetchSessionAutomations,
  fetchAutomations,
  fetchAutomationChats,
  changeAutomationChat,
  fetchAutomationRunResult,
  runAutomationAction,
  updateAutomation,
} from "./automations";
export {
  fetchSubagentTasks,
  fetchSubagentThread,
  cancelSubagentTask,
} from "./subagents";
export {
  fetchSkills,
  fetchSkillDetail,
  updateSkillEnabled,
  deleteSkill,
  searchMarketplaceSkills,
  fetchTrendingMarketplaceSkills,
  fetchMarketplaceSkillTrends,
  installMarketplaceSkill,
} from "./skills";
export {
  fetchSettings,
  fetchSettingsUsage,
  updateWebSearchSettings,
  updateNetworkSafetySettings,
  updateRuntimeConfigSettings,
} from "./settings";
export { fetchWorkspaces, fetchWorkspaceDirectories } from "./workspaces";
export {
  fetchCliApps,
  fetchInstalledCliApps,
  fetchCirnoFeatures,
  enableCirnoFeature,
  disableCirnoFeature,
  runCliAppAction,
} from "./apps";
export {
  startChannelConnect,
  pollChannelConnect,
  cancelChannelConnect,
  configureChannel,
  validateChannel,
} from "./channels";
export {
  fetchMcpPresets,
  fetchCustomMcpConfig,
  startMcpOAuth,
  fetchMcpOAuthStatus,
  completeMcpOAuth,
  cancelMcpOAuth,
  runMcpPresetAction,
  saveCustomMcpServer,
  importMcpConfig,
  updateMcpServerTools,
} from "./mcp";
export {
  fetchAutomaticModelAPI,
  fetchProviderModels,
  createModelConfiguration,
  updateModelConfiguration,
  deleteModelConfiguration,
  updateModelCallOrder,
  updateProviderSettings,
  createProviderSettings,
  loginProviderOAuth,
  completeProviderOAuth,
  cancelProviderOAuth,
  logoutProviderOAuth,
  fetchProviderBalance,
} from "./models";
export { listSlashCommands } from "./commands";
export { fetchSidebarState } from "./conversation-preferences";

export { fetchPromptPage } from "./prompt-directory";
