import { ListBox, Select } from "@heroui/react";
import { useTranslation } from "react-i18next";
import { currentLocale, setAppLanguage } from "@/i18n";
import { supportedLocales, type SupportedLocale } from "@/i18n/config";

export function LanguageSwitcher({ className }: { className?: string }) {
  const { t } = useTranslation();
  return <Select value={currentLocale()} aria-label={t("sidebar.language.ariaLabel")}
    onChange={value => { if (value !== null) void setAppLanguage(String(value) as SupportedLocale); }}>
    <Select.Trigger aria-label={t("sidebar.language.ariaLabel")} className={className}><Select.Value>{supportedLocales.find(option => option.code === currentLocale())?.nativeLabel}</Select.Value><Select.Indicator /></Select.Trigger>
    <Select.Popover><ListBox items={supportedLocales}>{option => <ListBox.Item id={option.code} textValue={option.nativeLabel}>
      {option.nativeLabel}<ListBox.ItemIndicator />
    </ListBox.Item>}</ListBox></Select.Popover>
  </Select>;
}
