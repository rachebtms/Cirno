import type { SettingsPayload } from "@/lib/contracts/settings";

const searchFirst = new Set([
  "aihubmix", "atomic_chat", "byteplus", "byteplus_coding_plan", "huggingface", "lm_studio",
  "modelscope", "novita", "ollama", "openrouter", "orcarouter", "ovms", "siliconflow", "vllm",
  "volcengine", "volcengine_coding_plan",
]);

export function catalogPolicy(provider: SettingsPayload["providers"][number] | undefined, query: string) {
  const manual = provider?.model_catalog === "unsupported"
    || provider?.auth_type === "oauth" && !["builtin", "hybrid"].includes(provider.model_catalog ?? "");
  const waitingForQuery = !manual && searchFirst.has(provider?.id ?? "") && query.trim().length < 2;
  return { manual, waitingForQuery, enabled: Boolean(provider?.configured) && !manual && !waitingForQuery };
}
