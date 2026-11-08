import { SETTINGS_NAV_ITEMS } from "./catalog";
import { settingsPanels } from "./panels";
import { createSettingsRegistry } from "./registry";

export const settingsSections = createSettingsRegistry(SETTINGS_NAV_ITEMS.map(section => ({ ...section, Panel: settingsPanels[section.key] })));
