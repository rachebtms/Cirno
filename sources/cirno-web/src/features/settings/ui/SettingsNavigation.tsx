import { useTabCompact } from "@/ui/layout/TabSurface";
import { Button, Modal, SearchField, Spinner } from "@heroui/react";
import { ChevronDown, LogOut, RotateCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { SettingsSectionKey } from "../contracts";
import { settingsSections } from "../modules";
import { NavigationList } from "./SettingsNavigationList";
import "./settings-navigation.css";

export function standaloneSectionTitle(section: SettingsSectionKey) {
  const standalone: Partial<Record<SettingsSectionKey, string>> = { apps: "Apps", automations: "Automations", skills: "Skills", channels: "Channels" };
  return settingsSections.get(section)?.fallback ?? standalone[section] ?? "Settings";
}

export interface SettingsNavigationProps {
  activeSection: SettingsSectionKey;
  onSelectSection: (section: SettingsSectionKey) => void;
  onLogout?: () => void;
  onRestart?: () => void;
  isRestarting?: boolean;
  restartPending?: boolean;
}

export function SettingsNavigation(props: SettingsNavigationProps) {
  const { t } = useTranslation();
  const mobile = useTabCompact(1024);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => { if (!mobile) setOpen(false); }, [mobile]);
  const active = props.activeSection === "capabilities" ? "browser" : props.activeSection;
  const label = t(`settings.nav.${active}`, { defaultValue: standaloneSectionTitle(active) });
  const search = <SearchField value={query} onChange={setQuery} aria-label={t("settings.navigationSearch")}>
    <SearchField.Group><SearchField.SearchIcon /><SearchField.Input placeholder={t("settings.navigationSearch")} /><SearchField.ClearButton /></SearchField.Group>
  </SearchField>;
  const navigation = <NavigationList active={active} query={query} onSelect={key => { props.onSelectSection(key); setOpen(false); setQuery(""); }} />;
  const actions = <div className="settings-navigation-actions">
    {props.onRestart && <Button variant="tertiary" onPress={() => { setOpen(false); props.onRestart?.(); }} isPending={props.isRestarting}
      aria-label={t(props.isRestarting ? "app.system.restarting" : "app.system.restartAction")} className={props.restartPending ? "text-warning" : undefined}>
      {props.isRestarting ? <Spinner size="sm" /> : <RotateCw size={16} />}{t(props.isRestarting ? "app.system.restarting" : "app.system.restartAction")}
    </Button>}
    {props.onLogout && <Button variant="tertiary" onPress={props.onLogout}><LogOut size={16} />{t("app.account.logout")}</Button>}
  </div>;
  if (mobile) return <aside className="settings-mobile-navigation">
    <Button variant="tertiary" aria-label={`${t("settings.sidebar.title")}: ${label}`} onPress={() => setOpen(true)}>{label}<ChevronDown size={16} /></Button>
    {props.restartPending && <p role="status" className="settings-mobile-restart">{t("settings.status.savedRestartApply")}</p>}
    <Modal.Backdrop isOpen={open} onOpenChange={setOpen} ><Modal.Container><Modal.Dialog className="settings-navigation-dialog">
        <Modal.CloseTrigger /><Modal.Header><Modal.Heading>{t("settings.sidebar.title")}</Modal.Heading></Modal.Header>
        <Modal.Body>{search}{navigation}</Modal.Body><Modal.Footer>{actions}</Modal.Footer>
      </Modal.Dialog></Modal.Container></Modal.Backdrop>
  </aside>;
  return <aside className="settings-desktop-navigation">
    <header>
      <span className="settings-navigation-title">{t("settings.sidebar.title")}</span>
    </header>{search}{navigation}
    {props.restartPending && <p role="status" className="settings-navigation-status">{t("settings.status.savedRestartApply")}</p>}
    {actions}
  </aside>;
}
