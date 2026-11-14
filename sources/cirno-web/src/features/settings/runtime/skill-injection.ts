import type { SkillInjectionSettings } from "@/features/skills/model/injection";
import { RUNTIME_CONFIG_FIELDS } from "../system/runtime-config-fields";
import type { RuntimeConfigController } from "./useRuntimeConfiguration";

const field = RUNTIME_CONFIG_FIELDS.find(item => item.path === "agents.defaults.always_skills")!;

export function skillInjectionSettings(state: RuntimeConfigController): SkillInjectionSettings {
  const names = () => String(state.value(field.path)).split("\n").filter(Boolean);
  return {
    names: names(),
    saving: state.saving === field.group,
    error: state.errors[field.group],
    setSelected: (name, selected) => state.commit(field, (
      selected ? [...new Set([...names(), name])] : names().filter(item => item !== name)
    ).join("\n")),
    retry: () => { void state.save(field.group); },
  };
}
