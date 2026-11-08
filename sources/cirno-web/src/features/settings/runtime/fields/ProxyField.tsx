import { useTranslation } from "react-i18next";
import { SharedProxyEditor } from "../../shared/SharedProxyEditor";
import type { ConfigurationFieldProps } from "./contracts";

export function ProxyField({ field, state, disabled }: ConfigurationFieldProps) {
  const { t } = useTranslation();
  return <SharedProxyEditor value={String(state.value(field.path))} disabled={disabled}
    onChange={next => state.change(field, next)} description={t("settings.runtimeConfig.fields.network_proxy.help")}
    addressProps={{ id: `runtime-${field.path}`, "aria-invalid": state.invalidField === field.path }} />;
}
