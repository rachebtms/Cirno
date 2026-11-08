import type { ProviderOperation } from "./operations";
import type { CirnoFeaturesPayload } from "@/lib/contracts/channels";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { CustomProviderDraft, ProviderForm } from "../providerForm";
export type ProviderSettingsEntry =
  | { kind: "manage" | "add"; origin?: "providers" }
  | { kind: "edit"; provider: string; origin?: "providers" };

export type ProviderSettingsProps = {
  entry: ProviderSettingsEntry;
  onConfigureProxy?: () => void;
  onClose: () => void;
  onProviderAdded?: (provider: string) => void;
  settings: SettingsPayload;
  cirnoFeatures: CirnoFeaturesPayload | null;
  featureAction: string | null;
  capabilityError: string | null;
  error?: string | null;
  providerForms: Record<string, ProviderForm>;
  visibleProviderKeys: Record<string, boolean>;
  editingProviderKeys: Record<string, boolean>;
  providerSaving: string | null;
  showBrandLogos: boolean;
  remoteBrowserAccess: boolean;
  onResetProviderDraft: (provider: string) => void;
  onToggleProviderKey: (provider: string) => void;
  onToggleProviderKeyEditing: (provider: string) => void;
  onChangeProviderForm: (provider: string, value: Partial<ProviderForm>) => void;
  onSaveProvider: (provider: string) => Promise<boolean>;
  onCreateCustomProvider: (draft: CustomProviderDraft) => Promise<SettingsPayload | null>;
  providerOperation?: ProviderOperation | null;
  onProviderOAuthLogin: (provider: string) => void;
  onProviderOAuthLogout: (provider: string) => void;
};
export type ProviderRow = SettingsPayload["providers"][number];
