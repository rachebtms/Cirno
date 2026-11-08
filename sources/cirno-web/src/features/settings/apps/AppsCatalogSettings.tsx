import { Alert, Button, SearchField, Spinner, Tabs } from "@heroui/react";
import { RotateCw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { catalogEntries } from "./model/catalog";
import type { AppsCatalogProps, AppsKindFilter } from "./model/contracts";
import { mcpOAuthStatusText } from "./model/status";
import { CliAppCard } from "./ui/CliAppCard";
import { CliReadyPanel } from "./ui/CliReadyPanel";
import { CustomMcpPanel } from "./ui/CustomMcpPanel";
import { McpCard } from "./ui/McpCard";
import "./apps.css";
export { DEFAULT_CUSTOM_MCP_FORM } from "./model/contracts";

export function AppsCatalogSettings(options: AppsCatalogProps) {
  const { t } = useTranslation();
  const items = catalogEntries(options.cliApps, options.mcpPresets, options.filter, options.query);
  const focused = options.cliFocusName ? options.cliApps?.apps.find(app => app.name === options.cliFocusName && app.installed) : null;
  const error = options.cliError || options.mcpError;
  const message = error || (!focused ? options.cliMessage || options.mcpMessage : null);
  const loading = options.mcpPresetsLoading && !options.mcpPresets || options.filter !== "mcp" && options.cliAppsLoading && !options.cliApps;
  const empty = options.query.trim() ? "empty" : ({ cli: "emptyApps", mcp: "emptyIntegrations", ready: "emptyReady" } as const)[options.filter];
  const browse: AppsKindFilter | null = options.query.trim() ? null : options.filter === "cli" ? "mcp" : options.cliApps?.apps.length ? "cli" : options.filter === "ready" ? "mcp" : null;
  const flow = options.mcpOAuthFlow;
  return <div className="apps-catalog">
    {flow && <p role="status" className="sr-only">{mcpOAuthStatusText(flow.status, options.mcpOAuthPopupBlocked, (key, fallback) => t(key, { defaultValue: fallback }), flow.completion_input)}</p>}
    <div className="catalog-toolbar"><SearchField value={options.query} onChange={options.onQueryChange} aria-label={t("settings.apps.searchPlaceholder")}><SearchField.Group><SearchField.SearchIcon /><SearchField.Input placeholder={t("settings.apps.searchPlaceholder")} /><SearchField.ClearButton /></SearchField.Group></SearchField>
      {!options.hideFilters && <Tabs selectedKey={options.filter} onSelectionChange={key => options.onFilterChange(key as AppsKindFilter)}><Tabs.ListContainer><Tabs.List aria-label={t("settings.apps.featured")}>
        {(["ready", "cli", "mcp"] as const).map(id => <Tabs.Tab key={id} id={id}>{t(`settings.apps.${({ ready: "filterAll", cli: "filterCli", mcp: "filterMcp" } as const)[id]}`)}<Tabs.Indicator /></Tabs.Tab>)}
      </Tabs.List></Tabs.ListContainer></Tabs>}
    </div>
    {message && <Alert status={error ? "danger" : "success"} role={error ? "alert" : "status"}><Alert.Content><Alert.Description>{message}</Alert.Description></Alert.Content><Button isIconOnly size="sm" variant="ghost" aria-label={t("common.close")} onPress={options.onDismissStatus}><X size={16} /></Button></Alert>}
    {focused && <CliReadyPanel app={focused} showBrandLogos={options.showBrandLogos} onBackToChat={options.onBackToChat} />}
    {options.requiresRestartPending && <Alert status="warning"><Alert.Content><Alert.Description>{t("settings.apps.restartRequired")}</Alert.Description></Alert.Content>
      {options.onRestart && <Button variant="secondary" isPending={options.isRestarting} onPress={options.onRestart}><RotateCw size={16} />{t("settings.actions.restart")}</Button>}</Alert>}
    {options.filter === "mcp" && <CustomMcpPanel options={options} />}
    <section aria-label={t(options.filter === "mcp" ? "settings.apps.mcpTools" : "settings.apps.featured")} className="catalog-results">
      <header><h2>{t(options.filter === "mcp" ? "settings.apps.mcpTools" : "settings.apps.featured")}</h2><span>{loading ? "—" : items.length}</span></header>
      <div className="catalog-grid">{items.map(item => item.kind === "cli" ? <CliAppCard key={item.id} app={item.app} options={options} /> : <McpCard key={item.id} preset={item.preset} options={options} />)}</div>
      {loading ? <div role="status" aria-label={t("settings.apps.loading")} aria-busy="true" className="catalog-loading"><Spinner size="sm" />{t("settings.apps.loading")}</div>
        : !items.length && !error && <div className="catalog-empty"><p>{t(`settings.apps.${empty}`)}</p>
          {options.query.trim() ? <Button variant="secondary" onPress={() => options.onQueryChange("")}>{t("settings.apps.clearSearch")}</Button> : browse && <Button variant="secondary" onPress={() => options.onFilterChange(browse)}>{t(browse === "cli" ? "settings.apps.browseApps" : "settings.apps.browseIntegrations")}</Button>}
        </div>}
    </section>
  </div>;
}
