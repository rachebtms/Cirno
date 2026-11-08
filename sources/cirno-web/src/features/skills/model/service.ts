import { useMemo } from "react";
import {
  deleteSkill,
  fetchMarketplaceSkillTrends,
  fetchSkillDetail,
  fetchTrendingMarketplaceSkills,
  installMarketplaceSkill,
  searchMarketplaceSkills,
  updateSkillEnabled,
  type WebUIMutationTransport,
} from "@/lib/api";
import type { MarketplaceSkillSummary } from "@/lib/contracts/skills";
import { useClient } from "@/providers/ClientProvider";
export function createSkillService(client: WebUIMutationTransport, getToken: () => string) {
  return {
    read: (name: string) => fetchSkillDetail(getToken(), name),
    update: (name: string, enabled: boolean) => updateSkillEnabled(client, name, enabled),
    remove: (name: string) => deleteSkill(client, name),
    popular: () => fetchTrendingMarketplaceSkills(getToken()),
    search: (query: string) => searchMarketplaceSkills(getToken(), query),
    trends: (ids: string[]) => fetchMarketplaceSkillTrends(getToken(), ids),
    install: (skill: MarketplaceSkillSummary) =>
      installMarketplaceSkill(client, skill.provider, skill.source, skill.skill_id, skill.version),
  };
}
export type SkillService = ReturnType<typeof createSkillService>;
export function useSkillService() {
  const { client, getToken } = useClient();
  return useMemo(() => createSkillService(client, getToken), [client, getToken]);
}
