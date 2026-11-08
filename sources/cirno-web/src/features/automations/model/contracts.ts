import type { SendAttachment, SendOptions } from "@/hooks/useCirnoStream";
import type {
  AutomationsPayload,
  SessionAutomationJob,
} from "@/lib/contracts/automations";
import type { ChatSummary } from "@/lib/contracts/conversations";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { ChangeAutomationChat } from "../binding/AutomationChatBinding";
import type { AutomationAction, AutomationFilter } from "./status";
export interface AutomationsPageProps {
  token?: string;
  payload: AutomationsPayload | null;
  titleOverrides?: Record<string, string>;
  sessions?: ChatSummary[];
  settingsSnapshot?: SettingsPayload | null;
  loading: boolean;
  filter: AutomationFilter;
  actionKey: string | null;
  error: string | null;
  onFilterChange: (value: AutomationFilter) => void;
  onAction: (
    action: AutomationAction,
    job: SessionAutomationJob,
  ) => void | Promise<void>;
  onRequestEdit: (job: SessionAutomationJob) => void;
  onRequestDelete: (job: SessionAutomationJob) => void;
  onStartChat?: (
    content: string,
    images?: SendAttachment[],
    options?: SendOptions,
    modelPreset?: string | null,
  ) => boolean | void | Promise<boolean | void>;
  onManageModels?: () => void;
  returnToDetailJob?: SessionAutomationJob | null;
  onReturnToDetailHandled?: () => void;
  onChangeChat?: ChangeAutomationChat;
}
