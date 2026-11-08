import type { Dispatch, ReactNode, SetStateAction } from "react";
import type { CirnoFeatureInfo } from "@/lib/contracts/channels";
import type { SettingsPayload, WebSearchSettingsUpdate } from "@/lib/contracts/settings";
import type { EditCompletion } from "../../shared/useEditCompletion";
export interface WebSettingsProps {
  embedded?: boolean;
  editCompletion?: EditCompletion;
  error?: string;
  enabled?: boolean;
  settings: SettingsPayload;
  form: WebSearchSettingsUpdate;
  keyVisible: boolean;
  keyEditing: boolean;
  saving: boolean;
  onChangeForm: Dispatch<SetStateAction<WebSearchSettingsUpdate>>;
  onChangeProvider: (provider: string) => void;
  onToggleKey: () => void;
  onToggleKeyEditing: () => void;
  onReset: () => void;
  onSave: () => void;
  showBrandLogos: boolean;
  onRestart?: () => void;
  isRestarting?: boolean;
  requiresRestartPending: boolean;
  olostepFeature?: CirnoFeatureInfo;
  olostepInstalling: boolean;
  capabilityError: string | null;
  children?: ReactNode;
}
