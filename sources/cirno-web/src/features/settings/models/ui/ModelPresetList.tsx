import { Button, Card, Chip, Switch } from "@heroui/react";
import { ArrowDown, ArrowUp, GripVertical } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ProviderIcon } from "../../shared/ProviderIcon";
import { modelPresetProviderKey } from "../modelCatalog";
import { formatModelContextWindow } from "@/lib/model-context-format";
import { settingsProviderConfigured } from "../modelValues";
import type { ModelSettings } from "../model/useModelSettings";
import type { ModelsSettingsProps } from "../model/contracts";
export function ModelPresetList({
  model,
  options,
}: {
  model: ModelSettings;
  options: ModelsSettingsProps;
}) {
  const { t } = useTranslation();
  return (
    <div
      ref={model.presetDrag.listRef}
      {...model.presetDrag.listProps}
      className="model-preset-list"
      role="list"
      aria-label={t("settings.models.callOrder")}
    >
      {model.presetRows.map(({ key, name, preset }, rowIndex) => {
        const position = model.presetDrag.previewKeys.indexOf(key);
        const ordered = position >= 0;
        const configured =
          preset &&
          settingsProviderConfigured(options.settings, preset.provider, preset.resolved_provider);
        return (
          <div
            key={key}
            role="listitem"
            data-call-order-index={position}
            data-preset-sort-key={key}
            style={{ order: (ordered ? position : rowIndex) * 2 }}
          >
            <Card data-preset-sort-surface={key} className="model-preset-card">
              <Card.Content
                className="model-preset-row"
                data-testid={`model-call-order-row-${name}`}
              >
                <Button
                  variant="ghost"
                  isIconOnly
                  className="model-preset-drag"
                  isDisabled={!ordered || model.callOrderBusy}
                  aria-label={`${preset?.name ?? name}. ${t("settings.models.dragToReorder")}`}
                  onPointerDown={(event) => model.presetDrag.start(event, key)}
                  onKeyDown={(event) => {
                    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
                      event.preventDefault();
                      model.moveCallOrderItem(position, event.key === "ArrowUp" ? -1 : 1);
                    }
                  }}
                >
                  <GripVertical size={17} />
                </Button>
                <Button
                  variant="ghost"
                  className="model-preset-open"
                  aria-haspopup="dialog"
                  isDisabled={!preset}
                  onPress={() => {
                    if (preset) void model.selectPreset(preset, key);
                  }}
                >
                  <ProviderIcon
                    provider={preset ? modelPresetProviderKey(preset, options.settings) : ""}
                    showBrandLogos={options.showBrandLogos}
                  />
                  <span className="model-preset-identity">
                    <span>{preset?.name ?? name}</span>
                    {preset && (
                      <span className="model-preset-meta">
                        {preset.model}
                        <span>{formatModelContextWindow(preset.context_window_tokens)}</span>
                        {preset.reasoning_effort && <span>{preset.reasoning_effort}</span>}
                      </span>
                    )}
                  </span>
                </Button>
                {position === 0 ? (
                  <Chip size="sm" variant="soft" color="accent">
                    {t("settings.models.primary")}
                  </Chip>
                ) : (
                  !ordered && (
                    <span className="provider-secondary">{t("settings.models.disabled")}</span>
                  )
                )}
                <Switch
                  aria-label={t(
                    ordered ? "settings.models.removeFromOrder" : "settings.models.addToOrder",
                  )}
                  isSelected={ordered}
                  isDisabled={model.callOrderBusy || (ordered && options.callOrder.length <= 1)}
                  onChange={() => {
                    if (ordered) model.removeCallOrderItem(position);
                    else if (preset) options.onChangeCallOrder([...options.callOrder, preset.id]);
                  }}
                >
                  <Switch.Content>
                    <Switch.Control>
                      <Switch.Thumb />
                    </Switch.Control>
                  </Switch.Content>
                </Switch>
                <div className="model-preset-order">
                  <Button
                    isIconOnly
                    size="sm"
                    variant="ghost"
                    aria-label={`${t("settings.models.callOrder")}: ${preset?.name ?? name} ↑`}
                    isDisabled={!ordered || position === 0 || model.callOrderBusy}
                    onPress={() => model.moveCallOrderItem(position, -1)}
                  >
                    <ArrowUp size={15} />
                  </Button>
                  <Button
                    isIconOnly
                    size="sm"
                    variant="ghost"
                    aria-label={`${t("settings.models.callOrder")}: ${preset?.name ?? name} ↓`}
                    isDisabled={
                      !ordered || position === options.callOrder.length - 1 || model.callOrderBusy
                    }
                    onPress={() => model.moveCallOrderItem(position, 1)}
                  >
                    <ArrowDown size={15} />
                  </Button>
                </div>
                {!configured && (
                  <p className="model-preset-unconfigured">
                    {t("settings.models.providerSetupRequired")}
                  </p>
                )}
              </Card.Content>
            </Card>
          </div>
        );
      })}
    </div>
  );
}
