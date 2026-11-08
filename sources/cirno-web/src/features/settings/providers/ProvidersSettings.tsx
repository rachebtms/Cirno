import { Alert, Button, Form, Modal } from "@heroui/react";
import { ChevronLeft, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ProviderIcon } from "@/features/settings/shared/ProviderIcon";
import type { ProviderSettingsProps } from "./model/contracts";
import { useProviderSetup } from "./model/useProviderSetup";
import { providerEditor } from "./model/providerEditor";
import { providerFormFromRow } from "./providerForm";
import { ProviderSearchList } from "./ProviderSearchList";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { ProviderEditor } from "./ui/ProviderEditor";
import { CustomProviderEditor } from "./ui/CustomProviderEditor";
import "./providers.css";
export type { ProviderSettingsEntry } from "./model/contracts";

export function ProvidersSettings(props: ProviderSettingsProps) {
  const { t } = useTranslation();
  const compact = useMediaQuery("(max-width: 639px)");
  const setup = useProviderSetup(props);
  const { step, provider, busy } = setup;
  const title =
    step.kind === "list"
      ? t("settings.providers.manageProviders")
      : step.kind === "custom"
        ? t("settings.providers.customProvider")
        : (provider?.name ?? t("settings.providers.addProvider"));
  const editable = step.kind === "custom" || step.kind === "provider";
  const canSave =
    step.kind === "custom"
      ? Boolean(setup.draft.name.trim() && setup.draft.apiBase.trim())
      : provider
        ? providerEditor(
            provider,
            props.providerForms[provider.id] ?? providerFormFromRow(provider),
          ).canSave
        : false;
  return (
    <Modal.Backdrop
      isOpen
      onOpenChange={(open) => {
        if (!open && !busy) setup.close();
      }}
      isDismissable={!busy}
      isKeyboardDismissDisabled={busy}
    >
      <Modal.Container size="md">
        <Modal.Dialog className="provider-setup-dialog">
          <Modal.Header className="provider-setup-heading">
            {setup.canGoBack && (
              <Button
                isIconOnly
                variant="ghost"
                isDisabled={busy}
                aria-label={t("settings.providers.backToProviders")}
                onPress={setup.back}
              >
                <ChevronLeft size={19} />
              </Button>
            )}
            <Modal.Heading>{title}</Modal.Heading>
            <Modal.CloseTrigger aria-label={t("common.close")} autoFocus={compact && step.kind === "picker"} isDisabled={busy} />
          </Modal.Header>
          {step.kind === "picker" ? (
            <Modal.Body className="provider-picker-body">
              <ProviderSearchList
                autoFocus={!compact}
                providers={setup.available}
                query={setup.query}
                onQueryChange={setup.setQuery}
                showBrandLogos={props.showBrandLogos}
                onSelect={(id) => setup.edit(id, true)}
                onCustom={setup.custom}
              />
            </Modal.Body>
          ) : step.kind === "list" ? (
            <Modal.Body>
              <div className="provider-connections">
                {setup.configured.map((row) => (
                  <Button
                    key={row.id}
                    variant="ghost"
                    className="provider-connection"
                    autoFocus={setup.lastProvider.current === row.id}
                    aria-label={row.name}
                    data-provider-return-focus={
                      setup.lastProvider.current === row.id ? "" : undefined
                    }
                    onPress={() => setup.edit(row.id, false)}
                  >
                    <ProviderIcon provider={row.id} showBrandLogos={props.showBrandLogos} />
                    <span>{row.name}</span>
                    <span className="provider-secondary">{t("settings.configure")}</span>
                  </Button>
                ))}
                {!setup.configured.length && (
                  <p className="provider-empty">{t("settings.byok.noConfiguredProviders")}</p>
                )}
              </div>
              <Button variant="secondary" onPress={setup.custom}>
                <Plus size={17} />
                {t("settings.providers.customProvider")}
              </Button>
              <Button
                variant="primary"
                onPress={() => {
                  setup.setQuery("");
                  setup.choose();
                }}
              >
                <Plus size={17} />
                {t("settings.providers.addProvider")}
              </Button>
            </Modal.Body>
          ) : (
            <Form
              onSubmit={(event) => {
                event.preventDefault();
                void setup.save();
              }}
              className="provider-form"
            >
              <Modal.Body>
                {step.kind === "custom" ? (
                  <CustomProviderEditor
                    draft={setup.draft}
                    onChange={(patch) => setup.setDraft((current) => ({ ...current, ...patch }))}
                    disabled={busy}
                    apiSupported={props.settings.provider_api_configuration_supported}
                    onConfigureProxy={props.onConfigureProxy}
                  />
                ) : (
                  provider && <ProviderEditor provider={provider} options={props} disabled={busy} />
                )}
                {(setup.error || props.error) && (
                  <Alert status="danger" role="alert">
                    <Alert.Description>{setup.error || props.error}</Alert.Description>
                  </Alert>
                )}
              </Modal.Body>
              {editable && (
                <Modal.Footer>
                  <Button variant="secondary" isDisabled={busy} onPress={setup.cancel}>
                    {t("settings.actions.cancel")}
                  </Button>
                  <Button type="submit" isPending={busy} isDisabled={!canSave}>
                    {t(
                      provider?.configured || provider?.auth_type === "oauth"
                        ? "settings.providers.saveProvider"
                        : "settings.providers.addProvider",
                    )}
                  </Button>
                </Modal.Footer>
              )}
            </Form>
          )}
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
