import { useCallback, useEffect, useState } from "react";
import { Copy, Link, RefreshCw, Unlink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ToggleButton } from "@/components/ui/toggle-button";
import { SettingsGroup, SettingsRow, SettingsSectionTitle } from "@/components/settings/shared/SettingsControls";
import type { CirnoClient } from "@/lib/cirno-client";

type Binding = { bound: boolean; enabled: boolean; username?: string; user_id?: string; notifications: string[]; webui_url: string };
type Pin = { pin: string; expires_at: number; ttl_seconds: number };
const categories = ["cirno", "operations", "conversations", "system"] as const;

export function TelegramBindingSettings({ client, onConfigure }: { client: CirnoClient; onConfigure: () => void }) {
  const { t } = useTranslation();
  const [binding, setBinding] = useState<Binding | null>(null);
  const [pin, setPin] = useState<Pin | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState("");
  const action = useCallback(<T,>(name: string, values = {}) => client.requestMutation<T>("instance.action", { action: `telegram.${name}`, values }), [client]);
  const reload = useCallback(async () => {
    const value = await action<Binding>("status");
    setBinding(value);
    return value;
  }, [action]);
  useEffect(() => {
    let disposed = false;
    void reload().then(value => { if (!disposed) setUrl(value.webui_url); }).catch(reason => { if (!disposed) setError((reason as Error).message); });
    return () => { disposed = true; };
  }, [reload]);
  const refreshPin = useCallback(async () => {
    const next = await action<Pin>("pin");
    setPin({ ...next, expires_at: Date.now() + next.ttl_seconds * 1000 });
    setSeconds(next.ttl_seconds);
  }, [action]);
  useEffect(() => {
    if (!pin) return;
    // Poll only while the owner has an active pairing challenge open.
    let disposed = false;
    let pending = false;
    const timer = window.setInterval(() => {
      setSeconds(Math.max(0, Math.ceil((pin.expires_at - Date.now()) / 1000)));
      if (pending) return;
      pending = true;
      void reload().then(async value => {
        if (disposed) return;
        if (value.bound) setPin(null);
        else if (Date.now() >= pin.expires_at) await refreshPin();
      }).catch(reason => { if (!disposed) setError((reason as Error).message); }).finally(() => { pending = false; });
    }, 1000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [pin, refreshPin, reload]);
  const run = async (work: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await work(); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  };
  const update = (values: object) => run(async () => { setBinding(await action<Binding>("settings", values)); });
  return <div className="settings-stack">
    <section>
      <div className="settings-section-heading"><SettingsSectionTitle>{t("settings.telegram.account")}</SettingsSectionTitle>
        <Button variant="ghost" size="sm" onClick={onConfigure}>{t("settings.telegram.configureBot")}</Button>
      </div>
      <p className="mb-4 text-sm leading-6 text-muted-foreground">{t("settings.telegram.help")}</p>
      {error && <p role="alert" className="mb-3 break-words text-sm text-destructive">{error}</p>}
      <SettingsGroup>
        <SettingsRow title={binding?.bound ? (binding.username ? `@${binding.username}` : binding.user_id) : t("settings.telegram.unbound")}
          description={binding?.bound ? t("settings.telegram.boundHelp") : t("settings.telegram.pinHelp")}>
          <Button variant={binding?.bound ? "ghost" : "default"} size="sm" disabled={busy || !binding}
            onClick={() => void run(async () => {
              if (binding?.bound) { setBinding(await action<Binding>("unbind")); setPin(null); }
              else await refreshPin();
            })}>
            {binding?.bound ? <Unlink className="mr-1.5 h-4 w-4" aria-hidden /> : <Link className="mr-1.5 h-4 w-4" aria-hidden />}
            {t(binding?.bound ? "settings.telegram.unbind" : "settings.telegram.generatePin")}
          </Button>
        </SettingsRow>
        {pin && <div className="border-t border-border/40 px-4 py-4 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <code className="font-mono text-2xl tracking-[0.2em] tabular-nums" aria-label={t("settings.telegram.pin")}>{pin.pin}</code>
            <div className="flex gap-1">
              <Button variant="ghost" size="icon" aria-label={t("settings.telegram.copyPin")} onClick={() => void run(async () => { await navigator.clipboard.writeText(`/bind ${pin.pin}`); })}><Copy className="h-4 w-4" /></Button>
              <Button variant="ghost" size="icon" disabled={busy} aria-label={t("settings.telegram.refreshPin")} onClick={() => void run(refreshPin)}><RefreshCw className="h-4 w-4" /></Button>
            </div>
          </div>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">{t("settings.telegram.expires", { seconds })}</p>
          <p className="text-sm leading-6 text-muted-foreground">{t("settings.telegram.sendPin", { command: `/bind ${pin.pin}` })}</p>
        </div>}
      </SettingsGroup>
    </section>
    {binding && <>
      <section><SettingsSectionTitle>{t("settings.telegram.delivery")}</SettingsSectionTitle><SettingsGroup>
        <SettingsRow title={t("settings.telegram.enabled")}><ToggleButton checked={binding.enabled} disabled={busy}
          ariaLabel={t("settings.telegram.enabled")} label={t(binding.enabled ? "settings.values.on" : "settings.values.off")}
          onChange={enabled => void update({ enabled })} /></SettingsRow>
        {categories.map(category => <SettingsRow key={category} title={t(category === "cirno" ? "settings.telegram.cirno" : `inbox.category.${category}`)}>
          <ToggleButton checked={binding.notifications.includes(category)} disabled={busy || !binding.enabled}
            ariaLabel={t(category === "cirno" ? "settings.telegram.cirno" : `inbox.category.${category}`)}
            label={t(binding.notifications.includes(category) ? "inbox.notify" : "inbox.muted")}
            onChange={enabled => void update({ notifications: enabled ? [...binding.notifications, category] : binding.notifications.filter(item => item !== category) })} />
        </SettingsRow>)}
      </SettingsGroup></section>
      <section><SettingsSectionTitle>{t("settings.telegram.actionLinks")}</SettingsSectionTitle><SettingsGroup>
        <div className="space-y-3 px-4 py-4 sm:px-6"><label className="block space-y-2 text-sm"><span>{t("settings.telegram.webuiUrl")}</span>
          <Input type="url" value={url} placeholder="https://cirno.example.com" onChange={event => setUrl(event.target.value)} />
        </label><p className="text-xs leading-5 text-muted-foreground">{t("settings.telegram.urlHelp")}</p>
          <Button size="sm" disabled={busy || url === binding.webui_url} onClick={() => void update({ webui_url: url.trim() })}>{t("features.save")}</Button>
        </div>
      </SettingsGroup></section>
    </>}
  </div>;
}
