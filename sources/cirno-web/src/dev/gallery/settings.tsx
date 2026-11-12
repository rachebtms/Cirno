import { useState } from "react";

import { AdvancedSettings, networkSafetyFormFromPayload } from "@/features/settings/capabilities/SecuritySettings";
import { WebSettings } from "@/features/settings/web/WebSettings";
import { webSearchDraftState, webSearchFormFromPayload } from "@/features/settings/web/model/form";
import { ChannelCard } from "@/features/channels/ui/ChannelCard";
import {channelRequirementErrors} from "@/features/channels/model/fieldValidation";
import {ChannelFieldGroups} from "@/features/channels/ui/fields/ChannelFieldGroups";
import { ChannelHelp } from "@/features/channels/ui/ChannelHelp";
import {ChannelLogo} from "@/features/channels/ui/ChannelLogo";
import {ChannelRuntimeError} from "@/features/channels/ui/ChannelRuntimeError";
import {ChannelStatusBadge} from "@/features/channels/ui/ChannelStatusBadge";
import { ChannelProviderPresets, ChannelSetupActions } from "@/features/channels/ui/setup/ChannelSetupHelpers";
import { ChannelValidationResult } from "@/features/channels/ui/ChannelValidationResult";
import type { ChannelConfigField, ChannelProviderPreset } from "@/channel-plugins/catalog";
import type { SettingsSectionKey } from "@/features/settings/contracts";
import { ModelAPIControl } from "@/features/settings/models/ModelAPIControl";
import { ProviderAPIControl } from "@/features/settings/providers/ProviderAPIControl";
import { ProviderParameterFields, type RequestParameterDraft } from "@/features/settings/providers/ProviderParameterFields";
import { ProviderSearchList } from "@/features/settings/providers/ProviderSearchList";
import { ReasoningEffortPicker } from "@/features/settings/models/ReasoningEffortPicker";
import { OverviewSettings } from "@/features/settings/overview/OverviewSettings";
import { SettingsNavigation } from "@/features/settings/ui/SettingsNavigation";
import { CatalogSkeleton } from "@/features/settings/shared/CatalogSkeleton";
import { Button as HeroButton, Label, ListBox, Select } from "@heroui/react";
import { ModelCatalogField } from "@/features/settings/models/ui/ModelCatalogField";
import { ProviderIcon } from "@/features/settings/shared/ProviderIcon";
import { RemoveActionButton } from "@/features/settings/shared/RemoveActionButton";
import { SettingsGroup, SettingsRow } from "@/features/settings/shared/SettingsControls";
import { SettingsHint } from "@/features/settings/shared/SettingsHint";
import { SettingsTextEditor } from "@/features/settings/shared/SettingsTextEditor";
import { SkeletonStatus } from "@/ui/feedback/SkeletonStatus";
import { AutomationCalendar } from "@/features/automations/calendar/AutomationCalendar";
import { AutomationRunDialogView } from "@/features/automations/runs/AutomationRunDialogView";
import { RunAtPicker } from "@/features/automations/ui/RunAtPicker";
import { TokenUsageCard } from "@/features/settings/TokenUsageCard";
import { Button } from "@/components/ui/button";
import type { ChannelValidationPayload, CirnoFeatureInfo } from "@/lib/contracts/channels";
import type { ModelAPIConfig } from "@/lib/contracts/models";
import type { SessionAutomationJob } from "@/lib/contracts/automations";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { Sample, StatePicker, type ComponentExample } from "./example";
import { useGalleryTranslation } from "./i18n";

const providers: SettingsPayload["providers"] = [
  { id: "openai", name: "OpenAI", configured: true, auth_type: "api_key", model_catalog: "builtin", model_api_configurable: true,
    request_apis: ["responses", "chat_completions"], provider_api_configurable: true },
  { id: "anthropic", name: "Anthropic", configured: true, auth_type: "api_key", model_catalog: "builtin", request_apis: ["anthropic_messages"] },
  { id: "openai_codex", name: "OpenAI Codex", configured: true, auth_type: "oauth", model_catalog: "builtin" },
  { id: "ollama", name: "Ollama", configured: true, auth_type: "api_key", model_catalog: "local" },
];

export const settings: SettingsPayload = {
  agent: { model: "gpt-5.4", provider: "openai", resolved_provider: "openai", has_api_key: true, model_preset: null,
    max_tokens: 8192, context_window_tokens: 200_000, temperature: 0.1, reasoning_effort: null, timezone: "UTC", tool_status_summary_max_chars: 40 },
  model_presets: [], model_call_order: [], model_call_order_editable: true,
  providers,
  web_search: { provider: "duckduckgo", max_results: 5, timeout: 30, providers: [
    { name: "duckduckgo", label: "DuckDuckGo", credential: "none" },
    { name: "brave", label: "Brave Search", credential: "api_key" },
    { name: "searxng", label: "SearXNG", credential: "base_url" },
  ] },
  web: { enable: true, search: { max_results: 5, timeout: 30 }, fetch: { use_jina_reader: true } },
  runtime: { config_path: "config.json", workspace_path: "workspace", health_host: "127.0.0.1", health_port: 8765,
    heartbeat: { enabled: true, interval_s: 1800 }, consolidation: { mode: "inline", learning: true } },
  advanced: { restrict_to_workspace: true, ssrf_whitelist_count: 0, webui_allow_local_service_access: true,
    webui_default_access_mode: "default", private_service_protection_enabled: true, mcp_server_count: 0,
    exec_enabled: true, exec_path_prepend_set: false, exec_path_append_set: false },
  requires_restart: false,
};

function usePreviewForm<T>(initial: T) {
  const [form, setForm] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const dirty = JSON.stringify(form) !== JSON.stringify(saved);
  return { form, setForm, dirty, save: () => setSaved(form) };
}

function FormStatus({ dirty }: { dirty: boolean }) {
  const { t } = useGalleryTranslation();
  return <p role="status" className="mt-4 text-xs text-muted-foreground">{t(dirty ? "controls.common.savingPreview" : "controls.common.savedPreview")}</p>;
}

function ModelPickerPreview() {
  const { t } = useGalleryTranslation();
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("gpt-5.4");
  const [effort, setEffort] = useState("medium");
  const [action, setAction] = useState<{ kind: "add" } | { kind: "configure"; provider: string } | null>(null);
  return <div className="settings-grid space-y-4">
    <SettingsGroup>
      <Select value={provider} onChange={key => { if (key !== null) { setProvider(String(key)); setModel(""); } }}>
        <Label>{t("settings.rows.provider", { ns: "common" })}</Label><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
        <Select.Popover><ListBox items={providers.slice(0, 2)}>{row => <ListBox.Item id={row.id} textValue={row.name}>{row.name}<ListBox.ItemIndicator /></ListBox.Item>}</ListBox></Select.Popover>
      </Select>
      <div className="provider-actions"><HeroButton variant="secondary" onPress={() => setAction({ kind: "add" })}>{t("settings.providers.addProvider", { ns: "common" })}</HeroButton>
        <HeroButton variant="ghost" onPress={() => setAction({ kind: "configure", provider })}>{t("settings.configure", { ns: "common" })}</HeroButton></div>
      <ModelCatalogField token="" provider={providers.find(row => row.id === provider)} value={model} onChange={setModel} />
      <ReasoningEffortPicker token="" provider={undefined} model={model}
        savedValues={["low", "medium", "high"]} value={effort} onChange={setEffort} />
    </SettingsGroup>
    <p role="status" className="text-xs text-muted-foreground">{provider} / {model} / {effort || t("settings.values.default", { ns: "common" })}{action ? ` · ${action.kind === "add" ? t("settings.providers.addProvider", { ns: "common" }) : t("controls.modelPickers.configure", { provider: action.provider })}` : ""}</p>
  </div>;
}

function ProviderIconsPreview() {
  const { t } = useGalleryTranslation();
  const [size, setSize] = useState<"regular" | "compact" | "fill">("regular");
  return <><StatePicker label={t("controls.providerIcons.size")} value={size} options={["regular", "compact", "fill"]} onChange={setSize} />
    <div className="flex flex-wrap gap-8">{providers.map((provider) => <Sample key={provider.id} label={provider.name}>
      <div className="flex items-center gap-3"><span className={size === "fill" ? "block h-12 w-12" : ""}>
        <ProviderIcon provider={provider.id} compact={size === "compact"} fill={size === "fill"} showBrandLogos={false} />
      </span></div>
    </Sample>)}</div></>;
}

function TextEditorPreview() {
  const { t } = useGalleryTranslation();
  const [value, setValue] = useState("Keep replies concise. Explain the reason for a change.");
  const [mode, setMode] = useState<"editable" | "disabled">("editable");
  return <><StatePicker label={t("controls.textEditor.state")} value={mode} options={["editable", "disabled"]} onChange={setMode} />
    <SettingsGroup><SettingsRow title={<SettingsHint description={t("controls.textEditor.hint")}>{t("controls.textEditor.instructions")}</SettingsHint>}>
      <SettingsTextEditor title={t("controls.textEditor.edit")} description={t("controls.textEditor.help")} value={value} disabled={mode === "disabled"}
        onSave={(next) => { if (!next.trim()) throw new Error(t("controls.textEditor.required")); setValue(next); }} />
    </SettingsRow></SettingsGroup>
    <pre role="status" className="mt-4 whitespace-pre-wrap rounded-control bg-surface-secondary p-4 text-sm">{value}</pre></>;
}

function RemovePresetPreview() {
  const { t } = useGalleryTranslation();
  const initial = [{ id: 1, nameKey: "controls.removePreset.defaultModel", primary: true }, { id: 2, nameKey: "controls.removePreset.codeAssistant", primary: false }];
  const [items, setItems] = useState(initial);
  return <div className="settings-grid"><SettingsGroup>
    {items.map((item) => <SettingsRow key={item.id} title={t(item.nameKey)}>
      <RemoveActionButton disabled={item.primary} aria-label={t("controls.removePreset.remove", { name: t(item.nameKey) })}
        aria-describedby={item.primary ? "gallery-primary-model-hint" : undefined}
        onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))}>{t("settings.actions.delete", { ns: "common" })}</RemoveActionButton>
    </SettingsRow>)}
  </SettingsGroup><p id="gallery-primary-model-hint" className="mt-4 text-xs text-muted-foreground">{t("controls.removePreset.primaryHint")}</p>
    <p role="status" className="mt-2 text-xs text-muted-foreground">{t("controls.removePreset.count", { count: items.length })}</p>
    <Button className="mt-3" variant="outline" size="sm" onClick={() => setItems(initial)}>{t("controls.common.reset")}</Button></div>;
}

function LoadingPreview() {
  const { t } = useGalleryTranslation();
  const [layout, setLayout] = useState<"apps" | "channels" | "skills">("apps");
  return <><StatePicker label={t("controls.loading.layout")} value={layout} options={["apps", "channels", "skills"]} onChange={setLayout} />
    <Sample label="CatalogSkeleton"><CatalogSkeleton label={t("controls.loading.catalog")} layout={layout} /></Sample>
    <div className="mt-6"><Sample label="SkeletonStatus"><SkeletonStatus label={t("settings.status.loading", { ns: "common" })} className="space-y-3">
      <div className="h-4 w-1/3 rounded bg-surface-secondary" /><div className="h-9 rounded-control bg-surface-secondary" />
    </SkeletonStatus></Sample></div></>;
}

function SidebarPreview() {
  const { t } = useGalleryTranslation();
  const [section, setSection] = useState<SettingsSectionKey>("models");
  const [pending, setPending] = useState(true);
  const [action, setAction] = useState<"logout" | "restart" | null>(null);
  return <div className="flex min-h-96 flex-col gap-6 lg:flex-row">
    <SettingsNavigation activeSection={section} onSelectSection={setSection} restartPending={pending}
      onLogout={() => setAction("logout")}
      onRestart={() => { setPending(false); setAction("restart"); }} />
    <div className="space-y-3 p-4"><p role="status" className="text-sm">{t("controls.common.selected", { value: t(`settings.nav.${section}`, { ns: "common" }) })}</p>
      <p className="text-xs text-muted-foreground">{t(action ? `controls.sidebar.${action}` : "controls.sidebar.hint")}</p>
      <Button variant="outline" size="sm" onClick={() => setPending((value) => !value)}>{t("controls.sidebar.toggleRestart")}</Button></div>
  </div>;
}

function ProviderSearchPreview() {
  const { t } = useGalleryTranslation();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<{ kind: "selected"; provider: string } | { kind: "custom" } | null>(null);
  return <><div className="flex h-[400px] flex-col overflow-hidden rounded-panel border pt-4">
    <ProviderSearchList providers={providers} showBrandLogos={false} query={query} onQueryChange={setQuery}
      onSelect={(provider) => setResult({ kind: "selected", provider })} onCustom={() => setResult({ kind: "custom" })} />
  </div><p role="status" className="mt-4 text-sm text-muted-foreground">{result?.kind === "selected" ? t("controls.common.selected", { value: result.provider }) : t(result ? `controls.providerSearch.${result.kind}` : "controls.providerSearch.hint")}</p></>;
}

function RequestParametersPreview() {
  const [form, setForm] = useState<RequestParameterDraft>({ extraHeaders: '{"X-Project":"gallery"}', extraQuery: "{}", extraBody: '{"service_tier":"auto"}' });
  return <div className="space-y-4"><ProviderParameterFields fields={["extra_headers", "extra_query", "extra_body"]} form={form}
    onChange={(next) => setForm((current) => ({ ...current, ...next }))} />
    <pre role="status" className="overflow-auto rounded-control bg-surface-secondary p-4 text-xs">{JSON.stringify(form, null, 2)}</pre></div>;
}

function RequestAPIPreview() {
  const { t } = useGalleryTranslation();
  const [providerAPI, setProviderAPI] = useState<ModelAPIConfig>({ supported_apis: ["responses", "chat_completions"], preferred_api: "responses" });
  const [modelAPI, setModelAPI] = useState<ModelAPIConfig | null>(null);
  return <div className="grid gap-8 md:grid-cols-2">
    <Sample label={t("controls.requestAPI.providerAPI")}><ProviderAPIControl value={providerAPI} onChange={setProviderAPI} /></Sample>
    <Sample label={t("controls.requestAPI.modelOverride")}><SettingsGroup><ModelAPIControl provider={providers[0]} automaticAPI="responses" value={modelAPI} onChange={setModelAPI} /></SettingsGroup></Sample>
    <pre role="status" className="overflow-auto rounded-control bg-surface-secondary p-4 text-xs md:col-span-2">{JSON.stringify({ providerAPI, modelAPI }, null, 2)}</pre>
  </div>;
}

type Usage = NonNullable<SettingsPayload["usage"]>;
const usage: Usage = (() => {
  const now = new Date();
  const days: Usage["days"] = Array.from({ length: 30 }, (_, index) => {
    const date = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - 29 + index));
    const scale = index % 7 === 0 ? 0 : index % 5 + 1;
    return { date: date.toISOString().slice(0, 10), input_tokens: scale * 4000, output_tokens: scale * 1000,
      cache_read_tokens: scale * 2000, cache_write_tokens: 0, cache_read_observed_input_tokens: scale * 3000,
      cache_write_observed_input_tokens: 0, total_tokens: scale * 5000, requests: scale * 2 };
  });
  const total = days.reduce((sum, day) => sum + day.total_tokens, 0);
  return { days, total_tokens: total, total_tokens_30d: total, total_tokens_365d: total,
    peak_day_tokens: Math.max(...days.map((day) => day.total_tokens)), current_streak_days: 3, longest_streak_days: 6,
    active_days_30d: days.filter((day) => day.total_tokens > 0).length, requests_30d: days.reduce((sum, day) => sum + day.requests, 0),
    model_days_30d: days.flatMap((day) => [
      { date: day.date, provider: "openai", model: "gpt-5.4", total_tokens: day.total_tokens * 0.6 },
      { date: day.date, provider: "anthropic", model: "claude-sonnet-4", total_tokens: day.total_tokens * 0.4 },
    ]) };
})();

function UsagePreview() {
  const { t } = useGalleryTranslation();
  const [mode, setMode] = useState<"active" | "empty" | "unavailable">("active");
  return <><StatePicker label={t("controls.usage.state")} value={mode} options={["active", "empty", "unavailable"]} onChange={setMode} />
    <TokenUsageCard usage={mode === "unavailable" ? undefined : mode === "empty" ? { ...usage, days: [], model_days_30d: [] } : usage} timeZone="UTC" /></>;
}

function OverviewPreview() {
  const { t } = useGalleryTranslation();
  const [section, setSection] = useState<SettingsSectionKey>("overview");
  return <><OverviewSettings settings={{ ...settings, usage }} showBrandLogos={false} onSelectSection={setSection} />
    <p role="status" className="mt-4 text-xs text-muted-foreground">{t("controls.overview.selected", { section: t(`settings.nav.${section}`, { ns: "common" }) })}</p></>;
}

function WebPreview() {
  const { t } = useGalleryTranslation();
  const [savedSettings, setSavedSettings] = useState(settings);
  const [form, setForm] = useState(webSearchFormFromPayload(settings));
  const [keyVisible, setKeyVisible] = useState(false);
  const [keyEditing, setKeyEditing] = useState(false);
  const { dirty } = webSearchDraftState(savedSettings, form);
  return <><WebSettings settings={savedSettings} form={form} saving={false} keyVisible={keyVisible} keyEditing={keyEditing}
    onChangeForm={setForm} onChangeProvider={(provider) => setForm((current) => ({ ...current, provider, apiKey: "", baseUrl: "" }))}
    onToggleKey={() => setKeyVisible((value) => !value)} onToggleKeyEditing={() => setKeyEditing((value) => !value)}
    onReset={() => setForm(webSearchFormFromPayload(savedSettings))}
    onSave={() => {
      setSavedSettings((current) => ({ ...current,
        web_search: { ...current.web_search, provider: form.provider,
          api_key_hint: form.apiKey ? "••••••••" : form.provider === current.web_search.provider ? current.web_search.api_key_hint : undefined,
          base_url: form.baseUrl, max_results: form.maxResults ?? current.web_search.max_results, timeout: form.timeout ?? current.web_search.timeout },
        web: { ...current.web, fetch: { use_jina_reader: form.useJinaReader ?? current.web.fetch.use_jina_reader } },
      })); setForm((current) => ({ ...current, apiKey: "" })); setKeyEditing(false);
    }} showBrandLogos={false} requiresRestartPending={false} olostepInstalling={false} capabilityError={null} />
    <p role="status" className="mt-4 text-xs text-muted-foreground">{t(dirty ? "controls.web.unsaved" : "controls.common.savedPreview")}</p></>;
}

function SafetyPreview() {
  const { form, setForm, dirty, save } = usePreviewForm(networkSafetyFormFromPayload(settings));
  return <><AdvancedSettings form={form} dirty={dirty} saving={false} requiresRestartPending={false}
    onChangeForm={setForm} onSave={save} /><FormStatus dirty={dirty} /></>;
}

const channel: CirnoFeatureInfo = {
  name: "gallery_channel", display_name: "Example channel", type: "channel", enabled: false, installed: true,
  configured: true, ready: true, status: "not_enabled", install_supported: true, requires_restart: false, runtime_status: "stopped",
  setup: { fields: [], official_url: "https://github.com/rachebtms/Cirno/tree/main/documents/configuration.md" },
};

function ChannelCatalogPreview() {
  const { t } = useGalleryTranslation();
  const [mode, setMode] = useState<"stopped" | "running" | "starting" | "failed" | "uninstalled">("stopped");
  const [selected, setSelected] = useState(false);
  const feature = { ...channel, display_name: t("controls.channelCatalog.exampleChannel"), enabled: mode === "running" || mode === "starting", installed: mode !== "uninstalled",
    runtime_status: mode === "uninstalled" ? "stopped" : mode, runtime_error: mode === "failed" ? t("controls.channelCatalog.error") : undefined };
  return <><StatePicker label={t("controls.channelCatalog.state")} value={mode} options={["stopped", "running", "starting", "failed", "uninstalled"]} onChange={setMode} />
    <div className="settings-grid"><SettingsGroup><ChannelCard feature={feature} showBrandLogos={false} actionKey={null}
      onSelect={() => setSelected(true)} onAction={(action, _name, options) => setMode(options?.installOnly ? "stopped" : action === "enable" ? "running" : "stopped")} /></SettingsGroup></div>
    <div className="mt-4 flex items-center gap-3"><ChannelLogo feature={feature} showBrandLogos={false} />
      <ChannelStatusBadge status={feature.runtime_status}>{t(`controls.channelCatalog.${feature.runtime_status}`)}</ChannelStatusBadge>
      <ChannelHelp feature={feature} /></div>
    <ChannelRuntimeError message={feature.runtime_error} />
    <p role="status" className="mt-4 text-xs text-muted-foreground">{t(selected ? "controls.channelCatalog.selected" : "controls.channelCatalog.hint")}</p></>;
}

function CredentialsPreview() {
  const { t } = useGalleryTranslation();
  const channelFields: ChannelConfigField[] = [
    { key: "bot_token", label: t("controls.credentials.botToken"), secret: true, section: "credentials", placeholder: t("controls.credentials.tokenPlaceholder") },
    { key: "server_url", label: t("controls.credentials.serverURL"), inputType: "url", section: "connection", optional: true },
    { key: "mode", label: t("controls.credentials.replyMode"), section: "behavior", options: [{ value: "mention", label: t("controls.credentials.mentions") }, { value: "all", label: t("controls.credentials.allMessages") }] },
    { key: "allow_from", label: t("controls.credentials.allowFrom"), section: "access", kind: "json", optional: true, placeholder: '["user-id"]' },
  ];
  const channelPresets: ChannelProviderPreset[] = [
    { id: "local", label: t("controls.credentials.local"), values: { server_url: "http://127.0.0.1:8080", mode: "mention" } },
    { id: "hosted", label: t("controls.credentials.hosted"), values: { server_url: "https://example.com", mode: "all" } },
  ];
  const [values, setValues] = useState<Record<string, string>>({ bot_token: "", server_url: "", mode: "mention", allow_from: "[]" });
  const [visibleSecrets, setVisibleSecrets] = useState<Record<string, boolean>>({});
  const [errorFields, setErrorFields] = useState<string[]>([]);
  const [notice, setNotice] = useState<{ kind: "applied"; preset: string } | { kind: "incomplete" | "saved" } | { kind: "helper"; message: string } | null>(null);
  const errors = Object.fromEntries(errorFields.map((key) => [key, t("controls.credentials.required")]));
  return <div className="space-y-5">
    <ChannelProviderPresets presets={channelPresets} onApply={(preset) => { setValues((current) => ({ ...current, ...preset.values })); setNotice({ kind: "applied", preset: preset.id }); }} />
    <ChannelFieldGroups fields={channelFields} requirements={[{ alternatives: [["bot_token"]] }]} values={values} visibleSecrets={visibleSecrets}
      errors={errors} onChange={(key, value) => { setValues((current) => ({ ...current, [key]: value })); setErrorFields([]); }}
      onToggleSecret={(key) => setVisibleSecrets((current) => ({ ...current, [key]: !current[key] }))} />
    <div className="flex flex-wrap items-center gap-3"><Button variant="outline" onClick={() => {
      const next = channelRequirementErrors(channelFields, [{ alternatives: [["bot_token"]] }], values, new Set(), new Set(), "required");
      setErrorFields(Object.keys(next)); setNotice({ kind: Object.keys(next).length ? "incomplete" : "saved" });
    }}>{t("controls.credentials.checkSave")}</Button><ChannelSetupActions feature={{ ...channel, display_name: t("controls.channelCatalog.exampleChannel") }} setup={{ actions: [{ id: "copy", label: t("controls.credentials.command"), copyText: "cirno" }] }} onNotice={(message) => setNotice(message ? { kind: "helper", message } : null)} /></div>
    <p role="status" className="text-xs text-muted-foreground">{notice?.kind === "helper" ? notice.message : notice?.kind === "applied" ? t("controls.credentials.applied", { name: t(`controls.credentials.${notice.preset}`) }) : t(notice ? `controls.credentials.${notice.kind}` : "controls.credentials.hint")}</p>
  </div>;
}

function ChannelValidationPreview() {
  const { t } = useGalleryTranslation();
  const [mode, setMode] = useState<"checking" | "connected" | "invalid">("connected");
  const validation: ChannelValidationPayload | null = mode === "checking" ? null : {
    name: channel.name, status: mode, identity: { name: "Example bot", workspace: "Gallery workspace" },
    checks: [{ id: "credentials", label: t("settings.channels.sections.credentials", { ns: "common" }), status: "pass" },
      { id: "connection", label: t("settings.channels.sections.connection", { ns: "common" }), status: mode === "invalid" ? "fail" : "pass", message: mode === "invalid" ? t("controls.channelValidation.expired") : undefined }],
    missing_fields: [], can_enable: mode === "connected", requires_restart: false,
  };
  return <><StatePicker label={t("controls.channelValidation.result")} value={mode} options={["checking", "connected", "invalid"]} onChange={setMode} />
    <ChannelValidationResult validation={validation} validating={mode === "checking"} feature={{ ...channel, display_name: t("controls.channelCatalog.exampleChannel") }} /></>;
}

function RunAtPreview() {
  const [value, setValue] = useState("2026-10-15T09:30");
  return <div className="max-w-md space-y-4"><RunAtPicker value={value} onChange={setValue} />
    <p role="status" className="text-sm text-muted-foreground">{value}</p></div>;
}

function AutomationCalendarPreview() {
  const { t, i18n } = useGalleryTranslation();
  const [month, setMonth] = useState(() => { const now = new Date(); return new Date(now.getFullYear(), now.getMonth(), 1); });
  const [mode, setMode] = useState<"scheduled" | "history" | "empty">("scheduled");
  const [selected, setSelected] = useState("");
  const jobs: SessionAutomationJob[] = mode === "empty" ? [] : [{ id: "gallery-reminder", name: "Weekly report", enabled: mode === "scheduled",
    schedule: { kind: "cron", expr: "30 9 * * 1", tz: "UTC" }, payload: { message: "Summarize this week's changes." },
    state: { next_run_at_ms: mode === "scheduled" ? new Date(month.getFullYear(), month.getMonth(), 15, 9, 30).getTime() : null,
      run_history: [{ run_at_ms: new Date(month.getFullYear(), month.getMonth(), 8, 9, 30).getTime(), status: "ok", duration_ms: 3200, webui_session_key: null },
        { run_at_ms: new Date(month.getFullYear(), month.getMonth(), 1, 9, 30).getTime(), status: "error", duration_ms: 1200, error: t("controls.automationCalendar.providerError"), webui_session_key: null }] } }];
  return <><StatePicker label={t("controls.automationCalendar.state")} value={mode} options={["scheduled", "history", "empty"]} onChange={setMode} />
    <div className="mb-4 flex flex-wrap items-center gap-3"><Button size="sm" variant="outline" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>{t("controls.automationCalendar.previousMonth")}</Button>
      <span className="text-sm">{new Intl.DateTimeFormat(i18n.language, { year: "numeric", month: "long" }).format(month)}</span>
      <Button size="sm" variant="outline" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>{t("controls.automationCalendar.nextMonth")}</Button></div>
    <AutomationCalendar jobs={jobs} month={month} locale={i18n.language} onInspect={(job) => setSelected(job.name)}
      renderRunDialog={(props) => <AutomationRunDialogView {...props} result={{ status: "loaded", response: "**运行结果**\n\n示例任务已处理当前项目更新。" }} onRetry={() => {}} />}
      copy={{
      planned: t("controls.automationCalendar.planned"), recorded: t("controls.automationCalendar.recorded"), running: t("controls.automationCalendar.running"), failed: t("controls.automationCalendar.failed"), completed: t("controls.automationCalendar.completed"), skipped: t("controls.automationCalendar.skipped"), system: t("controls.automationCalendar.system"),
      close: t("common.close", { ns: "common" }), noEntries: t("controls.automationCalendar.noEntries"), more: (count) => t("controls.automationCalendar.more", { count }),
    }} /><p role="status" className="mt-4 text-xs text-muted-foreground">{selected ? t("controls.automationCalendar.selected", { name: selected }) : t("controls.automationCalendar.hint")}</p></>;
}

const components = "sources/cirno-web/src/features/settings/";
export const settingsExamples: ComponentExample[] = [
  { title: "controls.modelPickers.title", files: ["models/ui/ModelCatalogField", "models/ReasoningEffortPicker"], Preview: ModelPickerPreview,
    description: "controls.modelPickers.description",
    options: "controls.modelPickers.options",
    code: '<ModelCatalogField token={token} provider={provider} value={model} onChange={setModel} />' },
  { title: "controls.providerIcons.title", files: ["shared/ProviderIcon"], Preview: ProviderIconsPreview,
    description: "controls.providerIcons.description", options: "controls.providerIcons.options",
    code: '<ProviderIcon provider="openai" showBrandLogos={false} compact />' },
  { title: "controls.textEditor.title", files: ["shared/SettingsTextEditor", "shared/SettingsHint"], Preview: TextEditorPreview,
    description: "controls.textEditor.description", options: "controls.textEditor.options",
    code: '<SettingsHint description="补充说明">标题</SettingsHint>\n<SettingsTextEditor title="编辑说明" value={value} onSave={setValue} />' },
  { title: "controls.removePreset.title", files: ["shared/RemoveActionButton"], Preview: RemovePresetPreview,
    description: "controls.removePreset.description", options: "controls.removePreset.options",
    code: '<RemoveActionButton disabled={referenced} onClick={deletePreset}>删除</RemoveActionButton>' },
  { title: "controls.loading.title", files: ["shared/CatalogSkeleton", "sources/cirno-web/src/ui/feedback/SkeletonStatus.tsx"], Preview: LoadingPreview,
    description: "controls.loading.description", options: "controls.loading.options",
    code: '<CatalogSkeleton label="正在加载目录" layout="channels" />\n<SkeletonStatus label="正在加载设置" className="space-y-3">{skeletons}</SkeletonStatus>' },
  { title: "controls.sidebar.title", files: ["ui/SettingsNavigation"], Preview: SidebarPreview,
    description: "controls.sidebar.description", options: "controls.sidebar.options",
    code: '<SettingsNavigation activeSection={section} onSelectSection={setSection} onBackToChat={back} onRestart={restart} restartPending />' },
  { title: "controls.providerSearch.title", files: ["providers/ProviderSearchList"], Preview: ProviderSearchPreview,
    description: "controls.providerSearch.description", options: "controls.providerSearch.options",
    code: '<ProviderSearchList providers={providers} query={query} onQueryChange={setQuery} showBrandLogos={false} onSelect={select} onCustom={custom} onClose={close} />' },
  { title: "controls.requestParameters.title", files: ["providers/ProviderParameterFields"], Preview: RequestParametersPreview,
    description: "controls.requestParameters.description", options: "controls.requestParameters.options",
    code: '<ProviderParameterFields fields={["extra_headers", "extra_query", "extra_body"]} form={draft} onChange={updateDraft} />' },
  { title: "controls.requestAPI.title", files: ["providers/ProviderAPIControl", "models/ModelAPIControl"], Preview: RequestAPIPreview,
    description: "controls.requestAPI.description", options: "controls.requestAPI.options",
    code: '<ProviderAPIControl value={api} onChange={setAPI} />\n<ModelAPIControl provider={provider} automaticAPI="responses" value={modelAPI} onChange={setModelAPI} />' },
  { title: "controls.usage.title", files: ["TokenUsageCard", "TokenUsageDetails", "TokenUsageModelTrend"], Preview: UsagePreview,
    description: "controls.usage.description", options: "controls.usage.options",
    code: '<TokenUsageCard usage={usage} timeZone="UTC" />' },
  { title: "controls.overview.title", files: ["overview/OverviewSettings"], Preview: OverviewPreview,
    description: "controls.overview.description", options: "controls.overview.options",
    code: '<OverviewSettings settings={settings} showBrandLogos={false} onSelectSection={setSection} />' },
  { title: "controls.web.title", files: ["web/WebSettings"], Preview: WebPreview,
    description: "controls.web.description", options: "controls.web.options",
    code: '<WebSettings settings={settings} form={form} onChangeForm={setForm} onSave={save} {...actions} />' },
  { title: "controls.safety.title", files: ["capabilities/SecuritySettings"], Preview: SafetyPreview,
    description: "controls.safety.description", options: "controls.safety.options",
    code: '<AdvancedSettings form={form} dirty={dirty} saving={false} requiresRestartPending={false} onChangeForm={setForm} onSave={save} />' },
  { title: "controls.channelCatalog.title", files: ["channels/ChannelCard", "sources/cirno-web/src/features/channels/model/presentation.ts", "channels/ChannelHelp"], Preview: ChannelCatalogPreview,
    description: "controls.channelCatalog.description", options: "controls.channelCatalog.options",
    code: '<ChannelCard feature={feature} showBrandLogos={false} actionKey={null} onSelect={select} onAction={act} />' },
  { title: "controls.credentials.title", files: ["sources/cirno-web/src/features/channels/ui/fields/ChannelFields.tsx", "sources/cirno-web/src/features/channels/ui/setup/ChannelSetupHelpers.tsx"], Preview: CredentialsPreview,
    description: "controls.credentials.description", options: "controls.credentials.options",
    code: '<ChannelFieldGroups fields={fields} requirements={requirements} values={values} visibleSecrets={visible} onChange={change} onToggleSecret={toggle} />' },
  { title: "controls.channelValidation.title", files: ["sources/cirno-web/src/features/channels/ui/ChannelValidationResult.tsx"], Preview: ChannelValidationPreview,
    description: "controls.channelValidation.description", options: "controls.channelValidation.options",
    code: '<ChannelValidationResult feature={feature} validation={validation} validating={checking} />' },
  { title: "controls.runAt.title", files: ["sources/cirno-web/src/features/automations/ui/RunAtPicker.tsx"], Preview: RunAtPreview,
    description: "controls.runAt.description", options: "controls.runAt.options",
    code: '<RunAtPicker value={runAt} onChange={setRunAt} />' },
  { title: "controls.automationCalendar.title", files: ["sources/cirno-web/src/features/automations/calendar/AutomationCalendar.tsx"], Preview: AutomationCalendarPreview,
    description: "controls.automationCalendar.description", options: "controls.automationCalendar.options",
    code: '<AutomationCalendar jobs={jobs} month={month} locale="zh-CN" copy={copy} onInspect={inspect} renderRunDialog={renderRunDialog} />' },
].map((example) => ({ ...example, files: example.files.map((file) => file.startsWith("sources/") ? file : `${components}${file}.tsx`) }));
