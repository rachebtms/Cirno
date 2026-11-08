/** Skills contracts shared by the browser and its transports. */

export interface SkillSummary {
  name: string;
  description: string;
  source: "home" | "builtin" | "plugin" | string;
  enabled?: boolean;
  deletable?: boolean;
  available: boolean;
  unavailable_reason?: string;
}

export interface SkillRequirements {
  bins: string[];
  env: string[];
  missing_bins: string[];
  missing_env: string[];
}

export interface SkillInstallOption {
  id: string;
  kind: string;
  label: string;
  command: string;
}

export interface SkillDetail extends SkillSummary {
  requirements: SkillRequirements | null;
  install_options?: SkillInstallOption[];
  raw_markdown: string;
}

export interface SkillsPayload {
  skills: SkillSummary[];
}

export interface SkillActionPayload extends SkillsPayload {
  last_action: {
    name: string;
    enabled: boolean;
    deleted: boolean;
  };
}

export interface MarketplaceSkillSummary {
  id: string;
  skill_id: string;
  name: string;
  source: string;
  provider: Exclude<MarketplaceProvider, "all">;
  installs: number;
  downloads?: number;
  url: string;
  installed: boolean;
  install_supported: boolean;
  metric: "installs_24h" | "installs_total";
  version?: string;
  verified?: boolean;
  requires_api_key?: boolean;
  rank?: number;
}

export type MarketplaceProvider = "all" | "skills_sh" | "skillhub";

export interface MarketplaceWarning {
  provider: Exclude<MarketplaceProvider, "all">;
  message: string;
}

export interface SkillsSearchPayload {
  warnings?: MarketplaceWarning[];
  query: string;
  skills: MarketplaceSkillSummary[];
  provider: MarketplaceProvider;
  install_supported: boolean;
}

export interface SkillsTrendingPayload {
  warnings?: MarketplaceWarning[];
  skills: MarketplaceSkillSummary[];
  period: "24h" | "trending" | "mixed";
  provider: MarketplaceProvider;
  install_supported: boolean;
}

export interface SkillsTrendsPayload {
  trends: Record<string, number[]>;
}

export interface SkillInstallPayload extends SkillsPayload {
  last_action: {
    installed: boolean;
    already_installed: boolean;
    name: string;
  };
}
