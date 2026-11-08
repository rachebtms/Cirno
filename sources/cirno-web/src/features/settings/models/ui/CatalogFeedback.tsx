import { Accordion, Alert, Button } from "@heroui/react";
import { useTranslation } from "react-i18next";
import type { RefObject } from "react";
import type { ProviderModelsPayload } from "@/lib/contracts/models";

export function CatalogFeedback({ payload, error, busy, onRetry, listRef }: {
  payload: ProviderModelsPayload | null; error: string | null; busy: boolean; onRetry: () => void; listRef: RefObject<HTMLElement | null>;
}) {
  const { t } = useTranslation();
  const stale = payload?.source === "stale" || payload?.source === "fallback";
  return <Alert role="alert" status="warning" className="model-catalog-feedback"><Alert.Content>
    <Alert.Description>{t("settings.models.catalogUnavailable")}</Alert.Description>
    {stale && <Alert.Description>{t(payload.source === "stale" ? "settings.models.catalogStale" : "settings.models.catalogFallback")}</Alert.Description>}
    {error && <Accordion><Accordion.Item id="error"><Accordion.Heading><Accordion.Trigger>{t("settings.models.catalogErrorDetails")}<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
      <Accordion.Panel><Accordion.Body><pre className="model-catalog-error">{error}</pre></Accordion.Body></Accordion.Panel>
    </Accordion.Item></Accordion>}
    <Button variant="secondary" size="sm" isPending={busy} onPress={() => { listRef.current?.focus(); onRetry(); }}>{t("common.retry")}</Button>
  </Alert.Content></Alert>;
}
