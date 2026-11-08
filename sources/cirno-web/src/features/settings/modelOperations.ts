import type { Dispatch, SetStateAction } from "react";
import type { TFunction } from "i18next";
import type { ApplySettingsPayload, PendingRestartSections } from "./contracts";
import type { ModelSettingsState } from "./models/useModelSettingsState";
import type { CirnoClient } from "@/lib/cirno-client";
import type { SettingsPayload } from "@/lib/contracts/settings";

export interface ModelSettingsActionsOptions {
  state: ModelSettingsState;
  settings: SettingsPayload | null;
  client: CirnoClient;
  t: TFunction;
  applyPayload: ApplySettingsPayload;

  setPendingRestartSections: Dispatch<SetStateAction<PendingRestartSections>>;
  setError: Dispatch<SetStateAction<string | null>>;
  onModelNameChange: (modelName: string | null) => void;
  providerBusy: boolean;
  installCapabilities: (names: string[]) => Promise<boolean>;
  configuredModelProviderOptions: Array<{ name: string; label: string }>;
}
