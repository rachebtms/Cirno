import { Alert, Button, Form, Modal } from "@heroui/react";
import { useTranslation } from "react-i18next";
import { SharedProxyEditor } from "./SharedProxyEditor";
import { useProxySetup } from "./useProxySetup";

export function SharedProxySetupDialog({ onClose, onSave, busy }: {
  busy: boolean;
  onClose: () => void;
  onSave: (address: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const setup = useProxySetup(onSave, onClose, busy);
  return <Modal.Backdrop isOpen onOpenChange={open => { if (!open && !setup.pending) onClose(); }} isDismissable={!setup.pending} isKeyboardDismissDisabled={setup.pending}><Modal.Container size="sm"><Modal.Dialog>
      <Form className="proxy-setup-form" validationBehavior="aria" onSubmit={event => { event.preventDefault(); void setup.save(); }}>
        <Modal.Header><Modal.Heading>{t("settings.runtimeConfig.fields.network_proxy.label")}</Modal.Heading>
          <p className="proxy-help">{t("settings.network.sharedProxyScope")}</p>
          <Modal.CloseTrigger isDisabled={setup.pending} />
        </Modal.Header>
        <Modal.Body>
          <SharedProxyEditor value={setup.address} onChange={setup.change} inputRef={setup.input} disabled={setup.pending} stackCredentials
            description={t("settings.runtimeConfig.fields.network_proxy.help")}
            addressProps={{ "aria-invalid": Boolean(setup.error), "aria-describedby": setup.error ? "shared-proxy-setup-error" : undefined }} />
          {setup.error && <Alert id="shared-proxy-setup-error" status="danger" role="alert"><Alert.Description>{setup.error}</Alert.Description></Alert>}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" isDisabled={setup.pending} onPress={onClose}>{t("settings.actions.cancel")}</Button>
          <Button type="submit" isPending={setup.pending} isDisabled={setup.pending || !setup.address.trim()}>{t(`settings.actions.${setup.pending ? "saving" : "save"}`)}</Button>
        </Modal.Footer>
      </Form>
    </Modal.Dialog></Modal.Container></Modal.Backdrop>;
}
