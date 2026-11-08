import { Alert, Button, Form, Input, Label, TextField, ToggleButton, ToggleButtonGroup } from "@heroui/react";
import { RefreshCw, Search } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { MarketplaceProvider, SkillSummary } from "@/lib/contracts/skills";
import { InlineError } from "@/ui/feedback/InlineError";
import { useSkillService } from "./model/service";
import { useMarketplaceSearch, useMarketplaceTrends } from "./model/useMarketplaceSearch";
import { useMarketplaceInstall } from "./model/useMarketplaceInstall";
import { MARKETPLACES } from "./model/presentation";
import { SkillActionDialog } from "./ui/SkillActionDialog";
import { MarketplaceGroups } from "./ui/MarketplaceGroups";
import { SkillsSkeleton } from "./ui/InstalledSkills";
import "./skills.css";
export function SkillsMarketplace({ installedSkills }: { installedSkills: SkillSummary[] }) {
  const { t } = useTranslation(),
    service = useSkillService();
  const search = useMarketplaceSearch(service),
    install = useMarketplaceInstall(service);
  const [provider, setProvider] = useState<MarketplaceProvider>("all");
  const records = search.searching
    ? (search.snapshot?.payload.skills ?? [])
    : (search.popular.value?.skills ?? []);
  const visible = records.filter((skill) => provider === "all" || skill.provider === provider);
  const trends = useMarketplaceTrends(
    service,
    visible.filter((skill) => skill.provider === "skills_sh").map((skill) => skill.id),
  );
  const loading = search.searching
    ? search.loading
    : search.popular.loading || search.popular.status === "idle";
  const error = search.searching ? search.error : search.popular.error;
  const warnings =
    (search.searching ? search.snapshot?.payload.warnings : search.popular.value?.warnings) ?? [];
  const retry = () => {
    void (search.searching ? search.retrySearch() : search.retryPopular());
  };
  const selected = install.selected;
  return (
    <section className="skills-marketplace">
      <Form
        className="skill-search-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (search.searching) void search.retrySearch();
        }}
      >
        <TextField value={search.query} onChange={search.change}>
          <Label className="sr-only">{t("settings.skills.marketplaceSearchLabel")}</Label>
          <Input placeholder={t("settings.skills.marketplaceSearchPlaceholder")} />
        </TextField>
        <Button
          type="submit"
          isIconOnly
          isDisabled={!search.searching}
          aria-label={t("settings.skills.marketplaceSearchLabel")}
        >
          <Search size={18} />
        </Button>
      </Form>
      <div className="skill-market-toolbar">
        <ToggleButtonGroup
          aria-label={t("settings.skills.marketplaceProviderFilter")}
          size="sm"
          selectionMode="single"
          disallowEmptySelection
          selectedKeys={new Set([provider])}
          onSelectionChange={(keys) => {
            const next = [...keys][0];
            if (next) setProvider(next as MarketplaceProvider);
          }}
        >
          {(["all", "skills_sh", "skillhub"] as const).map((id) => (
            <ToggleButton key={id} id={id}>
              {id === "all" ? t("settings.skills.marketplaceProviderAll") : MARKETPLACES[id].label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        <Button
          variant="ghost"
          size="sm"
          isIconOnly
          isDisabled={loading}
          aria-label={t("features.refresh")}
          onPress={retry}
        >
          <RefreshCw size={16} />
        </Button>
      </div>
      <header className="skill-market-intro">
        <h2>
          {search.searching
            ? t("settings.skills.marketplaceResultsFor", {
                query: search.snapshot?.query ?? search.query.trim(),
              })
            : t("settings.skills.marketplaceTrendingTitle")}
        </h2>
        {!search.searching && <p>{t("settings.skills.marketplaceTrendingDescription")}</p>}
        {loading && !!records.length && <p role="status">{t("settings.skills.marketplaceSearching")}</p>}
      </header>
      {warnings.map((warning) => (
        <Alert status="warning" role="alert" key={warning.provider}>
          <Alert.Content>
            <Alert.Description>
              {MARKETPLACES[warning.provider].label}: {warning.message}
            </Alert.Description>
          </Alert.Content>
        </Alert>
      ))}
      {error && (
        <div className="skill-retry">
          <InlineError message={error} />
          <Button variant="secondary" size="sm" onPress={retry}>
            {t("settings.skills.retry")}
          </Button>
        </div>
      )}
      {loading && !records.length ? (
        <SkillsSkeleton />
      ) : (
        <MarketplaceGroups
          skills={visible}
          installed={installedSkills}
          provider={provider}
          trends={trends.value?.trends ?? {}}
          onSelect={install.select}
        />
      )}
      {!loading && !visible.length && !error && (
        <p className="skill-empty">
          {t(
            search.searching
              ? "settings.skills.marketplaceEmpty"
              : "settings.skills.marketplaceTrendingUnavailable",
            { query: search.snapshot?.query ?? search.query.trim() },
          )}
        </p>
      )}
      {trends.error && (
        <div className="skill-retry">
          <InlineError message={trends.error} />
          <Button
            variant="ghost"
            size="sm"
            onPress={() => {
              void trends.refresh();
            }}
          >
            {t("settings.skills.retryTrends")}
          </Button>
        </div>
      )}
      {selected && (
        <SkillActionDialog
          title={t("settings.skills.marketplaceConfirmTitle", { name: selected.name })}
          description={
            <>
              <p>
                {t("settings.skills.marketplaceConfirmDescription", {
                  provider: MARKETPLACES[selected.provider].label,
                  source: selected.source,
                })}
              </p>
              <code>
                {selected.source}
                {selected.version && ` · v${selected.version}`}
              </code>
            </>
          }
          action={t("settings.skills.marketplaceConfirmInstall")}
          operation={install.operation}
          onClose={install.close}
          onConfirm={install.install}
        />
      )}
    </section>
  );
}
