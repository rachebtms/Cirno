import { Button, Input, Label, TextField, ToggleButton, ToggleButtonGroup } from "@heroui/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { InlineError } from "@/ui/feedback/InlineError";
import { SkeletonStatus } from "@/ui/feedback/SkeletonStatus";
import type { SkillSummary } from "@/lib/contracts/skills";
import { requestSkillsRefresh } from "@/lib/skill-events";
import { installedGroups, skillStatus, type InstalledFilter } from "../model/presentation";
export function InstalledSkills({
  skills,
  loading,
  error,
  onSelect,
}: {
  skills: SkillSummary[];
  loading: boolean;
  error: boolean;
  onSelect: (skill: SkillSummary) => void;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState<InstalledFilter>("all");
  const groups = installedGroups(skills, query, filter),
    disabled = skills.filter((skill) => skill.enabled === false).length;
  const counts = { all: skills.length, enabled: skills.length - disabled, disabled };
  return (
    <section className="skills-installed">
      <div className="skills-catalog-toolbar">
        <TextField value={query} onChange={setQuery}>
          <Label className="sr-only">{t("settings.skills.searchInstalled")}</Label>
          <Input placeholder={t("settings.skills.searchInstalled")} />
        </TextField>
        <ToggleButtonGroup
          selectionMode="single"
          disallowEmptySelection
          selectedKeys={new Set([filter])}
          onSelectionChange={(keys) => {
            const value = [...keys][0];
            if (value) setFilter(value as InstalledFilter);
          }}
          aria-label={t("settings.skills.installedTab")}
          size="sm"
        >
          {(["all", "enabled", "disabled"] as const).map((key) => (
            <ToggleButton key={key} id={key}>
              {t(`settings.skills.filter${key[0].toUpperCase()}${key.slice(1)}`)}{" "}
              <span>{loading || error ? "—" : counts[key]}</span>
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </div>
      {error && (
        <div className="skill-retry">
          <InlineError message={t("settings.skills.catalogLoadFailed")} />
          <Button variant="secondary" size="sm" onPress={requestSkillsRefresh}>
            {t("settings.skills.retry")}
          </Button>
        </div>
      )}
      {loading ? (
        <SkillsSkeleton />
      ) : groups.length ? (
        <div className="skill-groups">
          {groups.map((group) => (
            <section key={group.source}>
              <h3 className="skill-group-heading">
                {t(
                  `settings.skills.${{ home: "customGroup", builtin: "builtinGroup", other: "otherGroup" }[group.source]}`,
                )}{" "}
                <span>{group.skills.length}</span>
              </h3>
              <ul className="skills-list">
                {group.skills.map((skill) => {
                  const status = skillStatus(skill, t);
                  return (
                    <li key={`${skill.source}:${skill.name}`}>
                      <Button
                        variant="ghost"
                        className="skill-installed-row"
                        aria-label={t("settings.skills.openDetails", { name: skill.name })}
                        onPress={() => onSelect(skill)}
                      >
                        <span className="skill-summary">
                          <strong>{skill.name}</strong>
                          <span>{skill.description}</span>
                        </span>
                        <span
                          className={`skill-status skill-status-${status.tone}`}
                          title={skill.unavailable_reason}
                        >
                          <status.Icon size={15} />
                          {status.label}
                        </span>
                      </Button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      ) : (
        !error && (
          <p className="skill-empty">
            {t(skills.length ? "settings.skills.noMatching" : "settings.skills.empty")}
          </p>
        )
      )}
    </section>
  );
}
export function SkillsSkeleton() {
  const { t } = useTranslation();
  return (
    <SkeletonStatus label={t("settings.skills.loading")} className="skill-skeleton">
      {[0, 1, 2, 3].map((id) => (
        <div key={id}>
          <span />
          <span />
        </div>
      ))}
    </SkeletonStatus>
  );
}
