import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { SkillsLibrary } from "@/features/skills/SkillsLibrary";
import { useTheme } from "@/hooks/useTheme";
import { ClientProvider } from "@/providers/ClientProvider";
import { SKILLS_CHANGED_EVENT, isSkillsPayload } from "@/lib/skill-events";
import type { SkillDetail, SkillSummary } from "@/lib/contracts/skills";
import type { CirnoClient } from "@/lib/cirno-client";

const research: SkillDetail = {
  name: "research",
  source: "home",
  available: false,
  enabled: true,
  deletable: true,
  description:
    "Keep exact measurements, references and decisions for long-running scientific investigations. ".repeat(
      6,
    ),
  unavailable_reason: "Missing command: gh",
  raw_markdown: "# Research\nRecord exact measurements.\n\nKeep evidence with each conclusion.\n".repeat(90),
  requirements: {
    bins: ["gh"],
    env: ["RESEARCH_TOKEN"],
    missing_bins: ["gh"],
    missing_env: ["RESEARCH_TOKEN"],
  },
  install_options: [{ id: "brew", kind: "brew", label: "Install GitHub CLI", command: "brew install gh" }],
};
const paper = {
  id: "skills_sh:paper-reading",
  skill_id: "paper-reading",
  name: "Paper reading",
  source: "research-lab/paper-tools",
  provider: "skills_sh",
  installs: 12345,
  metric: "installs_24h",
  url: "https://skills.sh/research-lab/paper-tools",
  installed: false,
  install_supported: true,
  rank: 1,
};
const hub = {
  ...paper,
  id: "skillhub:analysis",
  skill_id: "analysis",
  name: "Data analysis",
  source: "analysis",
  provider: "skillhub",
  installs: 42,
  metric: "installs_total",
  url: "https://skillhub.cn/analysis",
  version: "1.2.0",
  rank: 1,
};
let installed: SkillSummary[] = [
  research,
  {
    name: "weather",
    description: "Read a weather forecast",
    source: "builtin",
    available: true,
    enabled: false,
  },
];
let trendRequests = 0,
  writes: { method: string; values: unknown }[] = [];
export function installSkillsFixtureApi() {
  const nativeFetch = window.fetch;
  window.fetch = async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input), location.origin);
    const body = (value: unknown) =>
      new Response(JSON.stringify(value), { headers: { "content-type": "application/json" } });
    if (url.pathname === "/v0/webui/skills/trending")
      return body({
        skills: [paper, hub],
        provider: "all",
        period: "mixed",
        install_supported: true,
        warnings: [{ provider: "skillhub", message: "A provider supplied partial catalog data" }],
      });
    if (url.pathname === "/v0/webui/skills/search")
      return body({
        skills: [paper, hub],
        query: url.searchParams.get("q"),
        provider: "all",
        install_supported: true,
      });
    if (url.pathname === "/v0/webui/skills/trends")
      return ++trendRequests === 1
        ? new Response("Fixture trend endpoint unavailable", { status: 503 })
        : body({ trends: { [paper.id]: [3, 4, 1, 7, 12, 8, 10, 13] } });
    if (url.pathname === "/v0/webui/skills/research")
      return body({ ...research, ...installed.find((skill) => skill.name === "research") });
    return nativeFetch(input, init);
  };
}
export function SkillsFixture() {
  useTheme();
  const { t } = useTranslation();
  const [skills, setSkills] = useState(installed),
    [actions, setActions] = useState(writes);
  useEffect(() => {
    const update = (event: Event) => {
      const payload = (event as CustomEvent).detail;
      if (isSkillsPayload(payload)) setSkills(payload.skills);
    };
    window.addEventListener(SKILLS_CHANGED_EVENT, update);
    return () => window.removeEventListener(SKILLS_CHANGED_EVENT, update);
  }, []);
  const client = useMemo(() => {
    const counts = new Map<string, number>();
    return {
      requestMutation: async (method: string, values: Record<string, unknown>) => {
        writes = [...writes, { method, values }];
        setActions(writes);
        const count = (counts.get(method) ?? 0) + 1;
        counts.set(method, count);
        if (method === "instance.action")
          return {
            validation: { valid: true, errors: [] },
            versions: [
              {
                revision: "snapshot-20261107",
                path: "/home/skills/.history/research/snapshot-20261107",
                validation: { valid: true, errors: [] },
              },
            ],
          };
        if (count === 1) throw new Error(`Fixture ${method} failed`);
        if (method === "skill.update")
          installed = installed.map((skill) =>
            skill.name === values.name ? { ...skill, enabled: values.enabled as boolean } : skill,
          );
        if (method === "skill.delete") installed = installed.filter((skill) => skill.name !== values.name);
        if (method === "skill.install")
          installed = [
            ...installed,
            {
              name: values.skill as string,
              description: "Read a paper with evidence",
              source: "home",
              enabled: true,
              available: true,
            },
          ];
        return {
          skills: installed,
          last_action: {
            name: values.name ?? values.skill,
            enabled: values.enabled,
            deleted: method === "skill.delete",
            installed: method === "skill.install",
            already_installed: false,
          },
        };
      },
    } as unknown as CirnoClient;
  }, []);
  return (
    <ClientProvider client={client} token="fixture">
      <main className="min-h-screen bg-background p-4 text-foreground sm:p-8">
        <div className="mx-auto max-w-3xl">
          <h1 className="mb-6 text-xl font-semibold">{t("settings.nav.skills")}</h1>
          <SkillsLibrary skills={skills} />
          <output hidden data-testid="skill-writes">
            {JSON.stringify(actions)}
          </output>
        </div>
      </main>
    </ClientProvider>
  );
}
