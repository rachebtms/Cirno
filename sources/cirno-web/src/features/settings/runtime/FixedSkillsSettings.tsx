import { Alert, Button, Checkbox, CheckboxGroup, Description, Label, SearchField } from "@heroui/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { SkillSummary } from "@/lib/contracts/skills";
import { RUNTIME_CONFIG_FIELDS } from "../system/runtime-config-fields";
import type { RuntimeConfigController } from "./useRuntimeConfiguration";

const field = RUNTIME_CONFIG_FIELDS.find(item => item.path === "agents.defaults.always_skills")!;
export function FixedSkillsSettings({ skills, state, loading }: {
  skills: SkillSummary[]; state: RuntimeConfigController; loading: boolean;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const selected = String(state.value(field.path)).split("\n").filter(Boolean);
  const declared = skills.filter(skill => skill.always && skill.available && skill.enabled !== false).map(skill => skill.name);
  const names = [...new Set([...skills.map(skill => skill.name), ...selected])].sort();
  const title = t("settings.runtimeConfig.fields.agents_defaults_always_skills.label");
  return <section className="configuration-section fixed-skills" aria-label={title}>
    <h2>{title}</h2>
    <p className="configuration-help">{t("settings.runtimeConfig.fields.agents_defaults_always_skills.help")}</p>
    <SearchField value={query} onChange={setQuery} aria-label={`${title} — ${t("settings.skills.searchInstalled")}`}>
      <SearchField.Group><SearchField.SearchIcon /><SearchField.Input /><SearchField.ClearButton /></SearchField.Group>
    </SearchField>
    <CheckboxGroup aria-label={title} value={[...new Set([...selected, ...declared])]} onChange={next => state.commit(field, next.filter(name => !declared.includes(name)).join("\n"))}
      isDisabled={loading || state.saving === field.group} className="fixed-skills-list">
      {names.filter(name => name.toLowerCase().includes(query.toLowerCase())).map(name => {
        const skill = skills.find(item => item.name === name);
        const available = skill?.enabled !== false && skill?.available;
        return <Checkbox key={name} value={name} isDisabled={declared.includes(name) || !available && !selected.includes(name)}>
          <Checkbox.Content><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><Label>{name}</Label></Checkbox.Content>
          {!available && <Description>{skill?.unavailable_reason || t("settings.skills.fixedUnavailable")}</Description>}
          {declared.includes(name) && <Description>{t("settings.skills.fixedDeclared")}</Description>}
        </Checkbox>;
      })}
    </CheckboxGroup>
    {state.errors[field.group] && <Alert status="danger"><Alert.Content>{state.errors[field.group]}</Alert.Content>
      <Button size="sm" onPress={() => { void state.save(field.group); }}>{t("common.retry")}</Button></Alert>}
  </section>;
}
