import type { ProviderRow } from "./contracts";
export const PROVIDER_GROUPS = [
  { id: "oauth", labelKey: "settings.providers.providerGroupOAuth", label: "OAuth" },
  { id: "api_key", labelKey: "settings.providers.providerGroupApiKey", label: "API Key" },
  { id: "local", labelKey: "settings.providers.providerGroupLocal", label: "Local" },
] as const;

const PROVIDER_SEARCH_ALIASES: Record<string, string> = {
  anthropic: "claude 克劳德 克勞德",
  deepseek: "深度求索 深度探索",
  zhipu: "智谱 智譜 glm z.ai",
  dashscope: "阿里 通义 通義 千问 千問 qwen",
  moonshot: "月之暗面 kimi",
  kimi_coding: "月之暗面 kimi coding",
  volcengine: "火山引擎 豆包 doubao",
  volcengine_coding_plan: "火山引擎 豆包 doubao",
  minimax: "海螺 稀宇",
  minimax_anthropic: "海螺 稀宇",
  siliconflow: "硅基流动 矽基流動 硅基流動",
  stepfun: "阶跃星辰 階躍星辰",
  xiaomi_mimo: "小米 mimo",
  longcat: "美团 美團",
  qianfan: "百度 千帆 文心",
  ant_ling: "蚂蚁 螞蟻 百灵 百靈",
};

export function providerGroups(providers: ProviderRow[], query: string) {
  const normalize = (value: string) => value.toLocaleLowerCase().replace(/[\s_.-]+/g, "");
  const match = normalize(query);
  const filtered = providers.filter(row => normalize(`${row.id} ${row.name} ${PROVIDER_SEARCH_ALIASES[row.id] ?? ""}`).includes(match));
  return PROVIDER_GROUPS.map(group => ({ ...group, providers: filtered.filter(row =>
    (row.auth_type === "oauth" ? "oauth" : row.model_catalog === "local" ? "local" : "api_key") === group.id)
  })).filter(group => group.providers.length);
}
