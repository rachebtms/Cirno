import type { ReactNode } from "react";
import { I18nProvider } from "react-aria-components";
import { useTranslation } from "react-i18next";

export function InterfaceProvider({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  return <I18nProvider locale={i18n.resolvedLanguage ?? i18n.language}>{children}</I18nProvider>;
}
