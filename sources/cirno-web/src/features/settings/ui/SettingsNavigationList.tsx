import { Button } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { SettingsSectionKey } from "../contracts";
import { settingsSections } from "../modules";

export function NavigationList({ active, query, onSelect }: {
  active: SettingsSectionKey;
  query: string;
  onSelect: (key: SettingsSectionKey) => void;
}) {
  const { t, i18n } = useTranslation();
  const items = settingsSections.navigation.map(item => ({ ...item, label: t(`settings.nav.${item.key}`, { defaultValue: item.fallback }) }))
    .filter(item => `${item.label} ${item.fallback}`.toLocaleLowerCase(i18n.language).includes(query.trim().toLocaleLowerCase(i18n.language)));
  const groups = [...new Set(items.map(item => item.group))];
  return <nav className="settings-navigation-list" aria-label={t("settings.sidebar.ariaLabel")}>
    {groups.map(group => <section key={group} className="settings-navigation-group">
      <p className="settings-navigation-group-title">{t(`settings.categories.${group}`)}</p>
      {items.filter(item => item.group === group).map(({ key, label, icon: Icon }) => <Button key={key}
        className="settings-navigation-item" variant={active === key ? "secondary" : "ghost"} onPress={() => onSelect(key)} aria-current={active === key ? "page" : undefined}>
        <Icon size={16} aria-hidden /><span>{label}</span>
      </Button>)}
    </section>)}
  </nav>;
}
