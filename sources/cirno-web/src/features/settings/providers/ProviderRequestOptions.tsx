import {
  parseProviderObject,
  providerJsonValue,
  type ProviderForm
} from "@/features/settings/providers/providerForm";
import { ToggleField } from "@/ui/fields/ToggleField";
import type { ModelAPIConfig } from "@/lib/contracts/models";
import { useTranslation } from "react-i18next";

type ProviderRequestOption = {
  kind: "priority" | "hosted_tool";
  titleKey: string;
  title: string;
  helpKey: string;
  help: string;
  toolType?: "web_search" | "x_search";
  defaultEnabled?: boolean;
  forceResponses?: boolean;
};

const PROVIDER_REQUEST_OPTIONS: Partial<Record<string, ProviderRequestOption[]>> = {
  openai_codex: [{
    kind: "priority",
    titleKey: "settings.providers.capabilityFastMode",
    title: "Fast mode",
    helpKey: "settings.providers.capabilityFastModeHelp",
    help: "Faster responses, increased usage.",
  }],
  openai: [{
    kind: "hosted_tool",
    titleKey: "settings.providers.capabilityOpenAISearch",
    title: "OpenAI web search",
    helpKey: "settings.providers.capabilityOpenAISearchHelp",
    help: "Allow compatible Responses API models to search the web. Search activity appears in chat.",
    toolType: "web_search",
    forceResponses: true,
  }],
  xai_grok: [{
    kind: "hosted_tool",
    titleKey: "settings.providers.capabilityXSearch",
    title: "X Search",
    helpKey: "settings.providers.capabilityXSearchHelp",
    help: "Allow supported Grok models to use xAI-hosted X Search. Search activity appears in chat.",
    toolType: "x_search",
    defaultEnabled: true,
  }],
};

function isHostedSearchTool(tool: unknown, toolType: "web_search" | "x_search"): boolean {
  if (!tool || typeof tool !== "object" || Array.isArray(tool)) return false;
  const configuredType = (tool as Record<string, unknown>).type;
  if (typeof configuredType !== "string") return false;
  return configuredType === toolType
    || (toolType === "web_search" && configuredType.startsWith("web_search_"));
}

function hasHostedSearchTool(value: unknown, toolType: "web_search" | "x_search"): boolean {
  return Array.isArray(value) && value.some((tool) => isHostedSearchTool(tool, toolType));
}

function providerRequestOptionEnabled(
  option: ProviderRequestOption,
  extraBody: Record<string, unknown>,
): boolean {
  if (option.kind === "priority") return extraBody.service_tier === "priority";
  if (Object.prototype.hasOwnProperty.call(extraBody, "tools")) {
    return hasHostedSearchTool(extraBody.tools, option.toolType!);
  }
  return option.defaultEnabled === true;
}

function updateProviderRequestOption(
  option: ProviderRequestOption,
  enabled: boolean,
  form: ProviderForm,
): Partial<ProviderForm> {
  const extraBody = { ...(parseProviderObject(form.extraBody) ?? {}) };
  if (option.kind === "priority") {
    if (enabled) extraBody.service_tier = "priority";
    else if (extraBody.service_tier === "priority") delete extraBody.service_tier;
  } else {
    const toolType = option.toolType!;
    const tools = Array.isArray(extraBody.tools)
      ? extraBody.tools.filter((tool) => !isHostedSearchTool(tool, toolType))
      : [];
    if (enabled) tools.push({ type: toolType });
    if (tools.length || option.defaultEnabled) {
      extraBody.tools = tools;
    } else {
      delete extraBody.tools;
    }
  }
  return {
    extraBody: providerJsonValue(extraBody),
    ...(option.forceResponses && enabled
      ? { api: { supported_apis: ["responses"], preferred_api: "responses" } satisfies ModelAPIConfig }
      : {}),
  };
}

export function ProviderRequestOptions({
  providerName,
  form,
  apiConfigurable,
  onChange,
}: {
  providerName: string;
  form: ProviderForm;
  apiConfigurable: boolean;
  onChange: (value: Partial<ProviderForm>) => void;
}) {
  const { t } = useTranslation();
  const options = (PROVIDER_REQUEST_OPTIONS[providerName] ?? [])
    .filter((option) => !option.forceResponses || apiConfigurable);
  if (options.length === 0) return null;
  const extraBody = parseProviderObject(form.extraBody) ?? {};

  const tx = (key: string, fallback: string) => t(key, { defaultValue: fallback });

  return <div className="provider-fields">{options.map(option => {
    const title = tx(option.titleKey, option.title);
    return <ToggleField key={option.titleKey} label={title} description={tx(option.helpKey, option.help)} selected={providerRequestOptionEnabled(option, extraBody)}
      onChange={enabled => onChange(updateProviderRequestOption(option, enabled, form))} />;
  })}</div>;
}
