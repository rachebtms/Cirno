/** Skills operations for the versioned Cirno API. */

import type {
  MarketplaceProvider,
  SkillActionPayload,
  SkillDetail,
  SkillInstallPayload,
  SkillsPayload,
  SkillsSearchPayload,
  SkillsTrendingPayload,
  SkillsTrendsPayload,
} from "@/lib/contracts/skills";
import {
  API_READ_TIMEOUT_MS,
  PACKAGE_MUTATION_TIMEOUT_MS,
  mutation,
  request,
} from "./transport";
import type { WebUIMutationTransport } from "./transport";

export async function fetchSkills(
  token: string,
  base: string = "",
): Promise<SkillsPayload> {
  return request<SkillsPayload>(
    `${base}/v0/webui/skills`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function fetchSkillDetail(
  token: string,
  name: string,
  base: string = "",
): Promise<SkillDetail> {
  return request<SkillDetail>(
    `${base}/v0/webui/skills/${encodeURIComponent(name)}`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function updateSkillEnabled(
  transport: WebUIMutationTransport,
  name: string,
  enabled: boolean,
): Promise<SkillActionPayload> {
  return mutation<SkillActionPayload>(transport, "skill.update", {
    name,
    enabled,
  });
}

export async function deleteSkill(
  transport: WebUIMutationTransport,
  name: string,
): Promise<SkillActionPayload> {
  return mutation<SkillActionPayload>(transport, "skill.delete", { name });
}

export async function searchMarketplaceSkills(
  token: string,
  query: string,
  provider: MarketplaceProvider = "all",
  base: string = "",
): Promise<SkillsSearchPayload> {
  const params = new URLSearchParams({ q: query, provider });
  return request<SkillsSearchPayload>(
    `${base}/v0/webui/skills/search?${params}`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function fetchTrendingMarketplaceSkills(
  token: string,
  provider: MarketplaceProvider = "all",
  base: string = "",
): Promise<SkillsTrendingPayload> {
  const params = new URLSearchParams({ provider });
  return request<SkillsTrendingPayload>(
    `${base}/v0/webui/skills/trending?${params}`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function fetchMarketplaceSkillTrends(
  token: string,
  skillIds: string[],
  base: string = "",
): Promise<SkillsTrendsPayload> {
  const params = new URLSearchParams();
  skillIds.forEach((id) => params.append("id", id));
  return request<SkillsTrendsPayload>(
    `${base}/v0/webui/skills/trends?${params}`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function installMarketplaceSkill(
  transport: WebUIMutationTransport,
  provider: Exclude<MarketplaceProvider, "all">,
  source: string,
  skill: string,
  version: string = "",
): Promise<SkillInstallPayload> {
  return mutation<SkillInstallPayload>(
    transport,
    "skill.install",
    { provider, source, skill, ...(version ? { version } : {}) },
    PACKAGE_MUTATION_TIMEOUT_MS,
  );
}
