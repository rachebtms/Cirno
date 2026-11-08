import { Button } from "@heroui/react";
import { useTranslation } from "react-i18next";
import { ToggleField } from "@/ui/fields/ToggleField";
import "./proxy.css";

export function ProxySettingsControl({ checked, disabled, onChange, onConfigure, className = "" }: {
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
  onConfigure?: () => void;
  className?: string;
}) {
  const { t } = useTranslation();
  const label = t("settings.network.useProxy");
  const description = t("settings.network.useProxyHelp");
  return <div data-proxy-control className={`proxy-consumer ${className}`}>
    {onConfigure ? <>
      <div className="proxy-consumer-copy"><span>{label}</span><p className="proxy-help">{description}</p></div>
      <Button variant="secondary" isDisabled={disabled} onPress={onConfigure}>{t("settings.network.configureProxy")}</Button>
    </> : <ToggleField label={label} description={description} selected={checked} disabled={disabled} onChange={onChange} />}
  </div>;
}
