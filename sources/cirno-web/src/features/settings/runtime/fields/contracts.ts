import type { RuntimeConfigField } from "../../system/runtime-config-fields";
import type { RuntimeConfigController } from "../useRuntimeConfiguration";
import type { SettingsPayload } from "@/lib/contracts/settings";

export interface ConfigurationFieldProps {
  field: RuntimeConfigField;
  state: RuntimeConfigController;
  settings: SettingsPayload;
  disabled: boolean;
}
