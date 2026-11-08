import { Button, Card, Chip, Dropdown } from "@heroui/react";
import { MoreHorizontal, Play, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CliAppInfo } from "@/lib/contracts/apps";
import type { AppsCatalogProps } from "../model/contracts";
import { CatalogLogo } from "./CatalogLogo";

export function CliAppCard({ app, options }: { app: CliAppInfo; options: AppsCatalogProps }) {
  const { t } = useTranslation();
  const busy = ["install", "update", "uninstall", "test"].some(action => options.cliActionKey === `${action}:${app.name}`);
  const action = (name: "install" | "update" | "uninstall" | "test") => options.onCliAction(name, app.name);
  return <Card role="article" aria-label={app.display_name} className="catalog-card"><Card.Content className="catalog-row">
    <CatalogLogo name={app.display_name} logo={app.logo_url} color={app.brand_color} show={options.showBrandLogos} cli />
    <div className="catalog-identity"><h3>{app.display_name}</h3><p>{app.description || app.requires || app.entry_point || app.name}</p><Chip size="sm" variant="soft">{t("settings.apps.cliLabel")}</Chip></div>
    <div className="catalog-actions">{app.installed ? <Dropdown>
      <Button variant="ghost" isIconOnly isDisabled={busy} isPending={busy} aria-label={`${t("common.moreActions")}: ${app.display_name}`}><MoreHorizontal size={18} /></Button>
      <Dropdown.Popover><Dropdown.Menu>
        <Dropdown.Item id="test" onAction={() => action("test")}><Play size={16} />{t("settings.cliApps.test")}</Dropdown.Item>
        <Dropdown.Item id="update" onAction={() => action("update")}><RefreshCw size={16} />{t("settings.cliApps.update")}</Dropdown.Item>
        <Dropdown.Item id="uninstall" variant="danger" onAction={() => action("uninstall")}><Trash2 size={16} />{t("settings.cliApps.uninstall")}</Dropdown.Item>
      </Dropdown.Menu></Dropdown.Popover>
    </Dropdown> : <Button variant="secondary" isDisabled={!app.install_supported || busy} isPending={busy}
      aria-label={t(app.install_supported ? "settings.cliApps.install" : "settings.cliApps.unavailable")} onPress={() => action("install")}><Plus size={16} />{t(app.install_supported ? "settings.cliApps.install" : "settings.cliApps.unavailable")}</Button>}</div>
  </Card.Content></Card>;
}
