import { Alert, Button, Form, Input, Link } from "@heroui/react";
import { ArrowRight, ExternalLink, Globe, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBrowserLocation } from "./model/useBrowserLocation";
import "./browser.css";
export function BrowserTab() {
  const { t } = useTranslation();
  const model = useBrowserLocation();
  return <section className="browser-panel" aria-label={t("workspace.browser")}>
    <Form className="browser-toolbar" onSubmit={event => { event.preventDefault(); model.navigate(); }}>
      <Button isIconOnly variant="ghost" aria-label={t("common.refresh")} isDisabled={!model.url} onPress={model.refresh}><RefreshCw size={17} /></Button>
      <Input aria-label={t("workspace.address")} placeholder="https://" value={model.address} onChange={event => model.setAddress(event.target.value)} autoComplete="url" spellCheck={false} />
      <Button type="submit" isIconOnly variant="secondary" aria-label={t("workspace.go")} isDisabled={!model.address.trim()}><ArrowRight size={18} /></Button>
      {model.url && <Link className="browser-external" href={model.url} target="_blank" rel="noopener noreferrer" aria-label={t("workspace.openExternal")}><ExternalLink size={18} /></Link>}
    </Form>
    <p className="browser-hint">{t("workspace.browserHint")}</p>
    {model.error && <Alert status="danger" role="alert"><Alert.Description>{model.error}</Alert.Description></Alert>}
    {model.url ? <iframe key={`${model.url}:${model.revision}`} src={model.url} title={t("workspace.browser")} sandbox="allow-scripts allow-forms allow-popups" referrerPolicy="no-referrer" className="browser-frame" />
      : <div className="browser-empty"><Globe size={30} strokeWidth={1.25} /><p>{t("workspace.enterUrl")}</p></div>}
  </section>;
}
