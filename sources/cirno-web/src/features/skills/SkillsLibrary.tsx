import { Tabs } from "@heroui/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { SkillSummary } from "@/lib/contracts/skills";
import { useClient } from "@/providers/ClientProvider";
import type { SkillInjectionSettings } from "./model/injection";
import { SkillHistory } from "./SkillHistory";
import { SkillsMarketplace } from "./SkillsMarketplace";
import { InstalledSkills } from "./ui/InstalledSkills";
import { SkillDetailDialog } from "./ui/SkillDetailDialog";
import "./skills.css";
export function SkillsLibrary({
  skills,
  loading = false,
  error = false,
  injection,
}: {
  skills: SkillSummary[];
  loading?: boolean;
  error?: boolean;
  injection?: SkillInjectionSettings;
}) {
  const { t } = useTranslation(),
    { client } = useClient();
  const [selected, setSelected] = useState<{ client: typeof client; skill: SkillSummary } | null>(null);
  return (
    <section className="skills-library">
      <Tabs defaultSelectedKey="installed">
        <Tabs.List aria-label={t("settings.skills.views")}>
          {["installed", "discover", "history"].map((view) => (
            <Tabs.Tab key={view} id={view}>
              {t(`settings.skills.${view}Tab`)}
              <Tabs.Indicator />
            </Tabs.Tab>
          ))}
        </Tabs.List>
        <Tabs.Panel id="installed">
          <InstalledSkills
            skills={skills}
            loading={loading}
            error={error}
            onSelect={(skill) => setSelected({ client, skill })}
          />
        </Tabs.Panel>
        <Tabs.Panel id="discover">
          <SkillsMarketplace installedSkills={skills} />
        </Tabs.Panel>
        <Tabs.Panel id="history">
          <SkillHistory client={client} />
        </Tabs.Panel>
      </Tabs>
      {selected?.client === client && (
        <SkillDetailDialog
          key={`${selected.skill.source}:${selected.skill.name}`}
          skill={selected.skill}
          injection={injection}
          onClose={() => setSelected(null)}
        />
      )}
    </section>
  );
}
