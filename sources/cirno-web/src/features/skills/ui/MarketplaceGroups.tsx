import { Button, Link } from "@heroui/react";
import { Check, ExternalLink, PackagePlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { MarketplaceProvider, MarketplaceSkillSummary, SkillSummary } from "@/lib/contracts/skills";
import { MARKETPLACES } from "../model/presentation";
import { TrendSparkline } from "./TrendSparkline";
export function MarketplaceGroups({
  skills,
  installed,
  provider,
  trends,
  onSelect,
}: {
  skills: MarketplaceSkillSummary[];
  installed: SkillSummary[];
  provider: MarketplaceProvider;
  trends: Record<string, number[]>;
  onSelect: (skill: MarketplaceSkillSummary) => void;
}) {
  const { t } = useTranslation();
  const names = new Set(installed.map((skill) => skill.name));
  return (
    <div className="skill-groups">
      {(Object.keys(MARKETPLACES) as (keyof typeof MARKETPLACES)[])
        .filter((source) => provider === "all" || provider === source)
        .map((source) => {
          const rows = skills.filter((skill) => skill.provider === source);
          return (
            !!rows.length && (
              <section key={source}>
                <div className="skill-market-heading">
                  <h3>{MARKETPLACES[source].label}</h3>
                  <Link
                    href={MARKETPLACES[source].url}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={t("settings.skills.marketplaceOpenProvider", {
                      provider: MARKETPLACES[source].label,
                    })}
                  >
                    <ExternalLink size={15} />
                  </Link>
                </div>
                <ul className="skills-list">
                  {rows.map((skill) => {
                    const installed = skill.installed || names.has(skill.skill_id),
                      label = t(
                        `settings.skills.${installed ? "marketplaceInstalled" : "marketplaceInstall"}`,
                      );
                    return (
                      <li key={skill.id} className="skill-market-row">
                        {skill.rank != null && <span className="skill-rank">{skill.rank}</span>}
                        <div className="skill-market-description">
                          <div>
                            <h4>{skill.name}</h4>
                            <Link
                              href={skill.url}
                              target="_blank"
                              rel="noreferrer"
                              aria-label={t("settings.skills.marketplaceOpen", {
                                name: skill.name,
                                provider: MARKETPLACES[source].label,
                              })}
                            >
                              <ExternalLink size={14} />
                            </Link>
                          </div>
                          <p>
                            {skill.source}
                            {skill.version && ` · v${skill.version}`}
                          </p>
                          {source === "skills_sh" && (
                            <p>
                              {t(
                                `settings.skills.${skill.metric === "installs_24h" ? "marketplaceInstalls24h" : "marketplaceInstalls"}`,
                                { count: skill.installs, formattedCount: skill.installs.toLocaleString() },
                              )}
                            </p>
                          )}
                          {!skill.install_supported && <p>{t("settings.skills.marketplaceNpxRequired")}</p>}
                        </div>
                        {source === "skills_sh" && <TrendSparkline values={trends[skill.id]} />}
                        <Button
                          variant="ghost"
                          size="sm"
                          isIconOnly
                          isDisabled={installed || !skill.install_supported}
                          aria-label={`${label} ${skill.name}`}
                          onPress={() => onSelect(skill)}
                        >
                          {installed ? <Check size={18} /> : <PackagePlus size={18} />}
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              </section>
            )
          );
        })}
    </div>
  );
}
