import { Hint } from "@/ui/feedback/Hint";
import { Button, Description, Dropdown, Label } from "@heroui/react";
import { ChevronDown, Layers, Settings2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { formatModelContextWindow } from "@/lib/model-context-format";
import type { ModelSelectorProps } from "./contracts";
import { PresetProviderIcon } from "./ProviderIcon";
import "./model-selection.css";

export function ModelSelector(props: ModelSelectorProps) {
  const { t } = useTranslation();
  const trigger = useRef<HTMLButtonElement>(null);
  const active = props.modelPresets?.find(preset => preset.id === props.modelPreset);
  const presets = props.modelPresets ?? [];
  const details = [...new Set([props.label, props.modelDetail, props.providerLabel,
    active?.contextWindowTokens ? formatModelContextWindow(active.contextWindowTokens) : null, active?.reasoningEffort].filter(Boolean))];
  useEffect(() => { if (props.attentionRequest) trigger.current?.focus(); }, [props.attentionRequest]);
  const canSelect = !props.needsSetup && ((Boolean(props.onPresetChange) && presets.length > 0) || Boolean(props.onManageModels));
  const button = <Button type="button" ref={trigger} className="composer-model-badge model-selector" variant="ghost"
    aria-label={props.label} onPress={props.needsSetup || !canSelect ? props.onClick : undefined}>
    {props.needsSetup ? <Layers size={16} aria-hidden /> : <PresetProviderIcon label={props.label} modelDetail={props.modelDetail} provider={props.provider}
      testId={`composer-model-logo${props.provider ? `-${props.provider}` : ""}`} />}
    <span>{props.label}</span>{canSelect && <ChevronDown size={14} aria-hidden />}
  </Button>;
  if (props.needsSetup) return button;
  const hint = (child: React.ReactNode) => <Hint triggerClassName="shrink" delay={400} content={details.join(" · ")}>{child}</Hint>;
  if (!canSelect) return hint(button);
  return <Dropdown>
    {hint(button)}
    <Dropdown.Popover className="model-selector-menu">
      <Dropdown.Menu aria-label={t("thread.composer.switchModel")} onAction={key => {
        if (key === ":manage") props.onManageModels?.();
        else {
          if (key !== props.modelPreset) props.onPresetChange?.(String(key));
          requestAnimationFrame(() => props.onRequestComposerFocus?.());
        }
      }}>
        <Dropdown.Section selectionMode="single" selectedKeys={props.modelPreset ? [props.modelPreset] : []}>
          {presets.map(preset => <Dropdown.Item key={preset.id} id={preset.id} textValue={preset.name ?? preset.id} isDisabled={!props.onPresetChange}>
            <PresetProviderIcon label={preset.name ?? preset.id} provider={preset.provider} modelDetail={preset.model} />
            <div className="model-selector-option"><Label>{preset.name ?? preset.id}</Label>
              <Description>{[preset.model, preset.contextWindowTokens ? formatModelContextWindow(preset.contextWindowTokens) : null, preset.reasoningEffort].filter(Boolean).join(" · ")}</Description>
            </div><Dropdown.ItemIndicator />
          </Dropdown.Item>)}
        </Dropdown.Section>
        {props.onManageModels && <Dropdown.Section><Dropdown.Item id=":manage" textValue={t("thread.composer.manageModels")}>
          <Settings2 size={16} />{t("thread.composer.manageModels")}
        </Dropdown.Item></Dropdown.Section>}
      </Dropdown.Menu>
    </Dropdown.Popover>
  </Dropdown>;
}
