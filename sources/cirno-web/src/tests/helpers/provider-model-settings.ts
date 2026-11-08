import { settingsPayload } from "../settings-test-utils";

export function providerModelSettings() {
  const value = settingsPayload();
  value.providers = [
    {
      id: "openai",
      name: "OpenAI",
      configured: true,
      api_key_hint: "configured",
      api_base: "https://api.openai.com/v1",
      model_catalog: "official",
      advanced_fields: ["extra_headers", "extra_body", "use_proxy"],
      model_api_configurable: true,
    },
    { id: "deepseek", name: "DeepSeek", configured: false },
  ];
  value.model_presets = value.model_presets.map((row) => ({
    ...row,
    provider: "openai",
  }));
  return value;
}
