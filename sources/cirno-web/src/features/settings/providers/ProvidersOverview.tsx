import { useEffect, useRef } from "react";
import { Button, Card } from "@heroui/react";
import { ChevronRight, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ProviderIcon } from "@/features/settings/shared/ProviderIcon";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { ProviderBalanceControl } from "./ProviderBalanceControl";
import "./providers.css";
interface ProvidersOverviewProps {
  restoreFocus?: string | null;
  onFocusRestored?: () => void;
  providers: SettingsPayload["providers"];
  showBrandLogos: boolean;
  onAdd: (trigger: HTMLButtonElement) => void;
  onSettingsChange: (settings: SettingsPayload) => void;
  onEdit: (id: string, trigger: HTMLButtonElement) => void;
}
export function ProvidersOverview({
  providers,
  showBrandLogos,
  onAdd,
  onEdit,
  onSettingsChange,
  restoreFocus,
  onFocusRestored,
}: ProvidersOverviewProps) {
  const { t } = useTranslation();
  const region = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!restoreFocus) return;
    const row = [
      ...(region.current?.querySelectorAll<HTMLButtonElement>("[data-provider-id]") ?? []),
    ].find((button) => button.dataset.providerId === restoreFocus);
    if (row) {
      row.focus({ preventScroll: true });
      onFocusRestored?.();
    }
  }, [restoreFocus, providers, onFocusRestored]);
  const configured = providers.filter((provider) => provider.configured);
  return (
    <section ref={region} aria-label={t("settings.nav.providers")} className="provider-overview">
      <div className="provider-overview-actions">
        <Button onClick={(event) => onAdd(event.currentTarget as HTMLButtonElement)}>
          <Plus size={17} />
          {t("settings.providers.addProvider")}
        </Button>
      </div>
      {!configured.length && (
        <Card>
          <Card.Content>
            <p className="provider-empty">{t("settings.byok.noConfiguredProviders")}</p>
          </Card.Content>
        </Card>
      )}
      {configured.map((provider) => (
        <Card key={provider.id} className="provider-overview-card">
          <Card.Content>
            <Button
              variant="ghost"
              className="provider-overview-connection"
              aria-label={provider.name}
              data-provider-id={provider.id}
              onClick={(event) => onEdit(provider.id, event.currentTarget as HTMLButtonElement)}
            >
              <ProviderIcon provider={provider.id} showBrandLogos={showBrandLogos} />
              <span className="provider-overview-identity">
                <span>{provider.name}</span>
                <code>{provider.id}</code>
                {provider.auth_type === "oauth" && (
                  <span className="provider-secondary">{t("settings.oauth.signedIn")}</span>
                )}
              </span>
              <ChevronRight size={17} />
            </Button>
            <ProviderBalanceControl provider={provider} onSaved={onSettingsChange} />
          </Card.Content>
        </Card>
      ))}
    </section>
  );
}
