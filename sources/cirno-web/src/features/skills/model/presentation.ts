import type { TFunction } from "i18next";
import { Check, CircleAlert, PowerOff } from "lucide-react";

import type { SkillSummary } from "@/lib/contracts/skills";

const SOURCE_LABELS: Record<string, string> = {
  home: "sourceHome",
  builtin: "sourceBuiltin",
  plugin: "sourcePlugin",
};

export function skillStatus(skill: SkillSummary, t: TFunction) {
  if (skill.enabled === false)
    return {
      label: t("settings.skills.statusDisabled"),
      tone: "muted" as const,
      Icon: PowerOff,
    };
  if (skill.available)
    return {
      label: t("settings.skills.statusEnabled"),
      tone: "success" as const,
      Icon: Check,
    };
  return { label: t("settings.skills.statusNeedsSetup"), tone: "warning" as const, Icon: CircleAlert };
}

export function skillSourceLabel(source: string, t: TFunction): string {
  const key = SOURCE_LABELS[source];
  return key ? t(`settings.skills.${key}`) : source;
}

export const MARKETPLACES = {
  skills_sh: { label: "skills.sh", url: "https://skills.sh/trending" },
  skillhub: { label: "SkillHub", url: "https://skillhub.cn" },
} as const;
export type InstalledFilter = "all" | "enabled" | "disabled";
export function installedGroups(skills: SkillSummary[], query: string, filter: InstalledFilter) {
  const needle = query.trim().toLocaleLowerCase();
  const filtered = skills.filter(
    (skill) =>
      (filter === "all" || (skill.enabled !== false) === (filter === "enabled")) &&
      (!needle || `${skill.name}\n${skill.description}`.toLocaleLowerCase().includes(needle)),
  );
  return (["home", "builtin", "other"] as const)
    .map((source) => ({
      source,
      skills: filtered.filter((skill) =>
        source === "other" ? !["home", "builtin"].includes(skill.source) : skill.source === source,
      ),
    }))
    .filter((group) => group.skills.length);
}
