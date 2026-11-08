import {
  Alert,
  Button,
  Input,
  Label,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
} from "@heroui/react";
import { RotateCcw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useClient } from "@/providers/ClientProvider";
import { InlineError } from "@/ui/feedback/InlineError";
import { ChannelSkeleton } from "./ui/ChannelSkeleton";
import type { ChannelsSettingsProps } from "./model/contracts";
import type { ChannelFilter } from "./model/catalog";
import { useChannelCatalog } from "./model/useChannelCatalog";
import { useChannelSelection } from "./model/useChannelSelection";
import { ChannelCard } from "./ui/ChannelCard";
import { ChannelDialog } from "./ui/ChannelDialog";
import "./channels.css";
export function ChannelsSettings(props: ChannelsSettingsProps) {
  const { t } = useTranslation(),
    { client } = useClient();
  const catalog = useChannelCatalog(client, props.cirnoFeatures, t);
  const {
    channels,
    query,
    filter: activeFilter,
    groups,
    changeQuery: setQuery,
    changeFilter: setFilter,
  } = catalog;
  const state = useChannelSelection(client, props.onBeforeCloseChange),
    selected = channels.find(
      (channel) => channel.name === state.selected?.name,
    );
  const restartRequired =
    props.requiresRestartPending ||
    Boolean(props.cirnoFeatures?.requires_restart);
  return (
    <div className="channel-settings">
      <div className="channel-toolbar">
        <TextField type="search" value={query} onChange={setQuery}>
          <Label className="sr-only">{t("settings.channels.search")}</Label>
          <Input placeholder={t("settings.channels.search")} />
        </TextField>
        <ToggleButtonGroup
          selectionMode="single"
          disallowEmptySelection
          selectedKeys={new Set([activeFilter])}
          onSelectionChange={(keys) => setFilter([...keys][0] as ChannelFilter)}
          aria-label={t("settings.nav.channels")}
          size="sm"
        >
          {(["all", "enabled"] as const).map((value) => (
            <ToggleButton key={value} id={value}>
              {t(
                value === "all"
                  ? "settings.channels.filterAll"
                  : "settings.channels.filterEnabled",
              )}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </div>
      {props.error && !selected && (
        <div className="channel-error">
          <InlineError message={props.error} />
          <Button
            variant="ghost"
            size="sm"
            isIconOnly
            aria-label={t("common.close")}
            onPress={props.onDismissStatus}
          >
            <X size={16} />
          </Button>
        </div>
      )}
      {restartRequired && (
        <Alert status="warning">
          <Alert.Content>
            <Alert.Description>
              {t("settings.channels.restartRequired")}
            </Alert.Description>
          </Alert.Content>
          {props.onRestart && (
            <Button
              size="sm"
              variant="secondary"
              onPress={props.onRestart}
              isPending={props.isRestarting}
            >
              <RotateCcw size={16} />
              {t("app.system.restart")}
            </Button>
          )}
        </Alert>
      )}
      {props.loading && !props.cirnoFeatures ? (
        <ChannelSkeleton label={t("settings.channels.loading")} />
      ) : groups.length ? (
        groups.map((group) => (
          <section key={group.key} aria-label={group.label}>
            <h3 className="channel-group-heading">{group.label}</h3>
            <div className="channel-cards">
              {group.channels.map((feature) => (
                <ChannelCard
                  key={feature.name}
                  feature={feature}
                  showBrandLogos={props.showBrandLogos}
                  actionKey={props.actionKey}
                  restartRequired={restartRequired}
                  onAction={props.onAction}
                  onRestart={props.onRestart}
                  isRestarting={props.isRestarting}
                  onSelect={(connect) => state.select(feature.name, connect)}
                />
              ))}
            </div>
          </section>
        ))
      ) : (
        !props.error && (
          <p className="channel-empty">
            {t(
              channels.length
                ? "settings.channels.noResults"
                : "settings.channels.empty",
            )}
          </p>
        )
      )}
      {selected && (
        <ChannelDialog feature={selected} state={state} settings={props} />
      )}
    </div>
  );
}
