import { Alert, Button, Card, Chip } from "@heroui/react";
import { Check } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { CliAppInfo } from "@/lib/contracts/apps";
import { copyTextToClipboard } from "@/lib/clipboard";
import { CatalogLogo } from "./CatalogLogo";

export function CliReadyPanel({ app, showBrandLogos, onBackToChat }: { app: CliAppInfo; showBrandLogos: boolean; onBackToChat: () => void }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const copy = async () => {
    if (await copyTextToClipboard(t("settings.cliApps.readyPrompt", { name: app.name }))) { setCopied(true); setError(""); }
    else setError(t("common.copyFailed"));
  };
  return <Card><Card.Content className="catalog-row">
    <CatalogLogo name={app.display_name} logo={app.logo_url} color={app.brand_color} show={showBrandLogos} cli />
    <div className="catalog-identity"><h3>{app.display_name}</h3><code>@{app.name} · {app.entry_point || app.name}</code><Chip variant="soft" color="success"><Check size={13} />{t("settings.cliApps.readyStatus")}</Chip></div>
    <div className="catalog-actions"><Button variant="secondary" onPress={() => void copy()}>{copied ? t("settings.cliApps.readyCopied") : t("settings.cliApps.readyTry", { name: app.name })}</Button>
      <Button onPress={onBackToChat}>{t("settings.cliApps.openChat")}</Button></div>
    {error && <Alert status="danger" role="alert"><Alert.Description>{error}</Alert.Description></Alert>}
  </Card.Content></Card>;
}
