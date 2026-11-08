import { Accordion, Alert, Button, Card, Modal } from "@heroui/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ToggleField } from "@/ui/fields/ToggleField";
import "./feature.css";

export function SettingsAdvancedOptions({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return <Accordion><Accordion.Item id="advanced"><Accordion.Heading><Accordion.Trigger>{t("settings.runtimeConfig.advancedOptions")}<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
    <Accordion.Panel><Accordion.Body className="settings-feature-options">{children}</Accordion.Body></Accordion.Panel>
  </Accordion.Item></Accordion>;
}

export function SettingsFeature({ title, enabled, onChange, disabled, initialOpen = false, error, children, onBeforeClose }: {
  title: string; enabled: boolean; onChange: (enabled: boolean) => void; disabled?: boolean; initialOpen?: boolean; error?: string;
  children?: ReactNode; onBeforeClose?: () => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(initialOpen && enabled);
  const [closing, setClosing] = useState(false);
  const [closeError, setCloseError] = useState("");
  const section = useRef<HTMLElement>(null);
  const closeRequest = useRef(false);
  useEffect(() => {
    if (initialOpen && enabled) { setOpen(true); section.current?.scrollIntoView({ block: "nearest" }); }
  }, [initialOpen, enabled]);
  const close = async () => {
    if (closeRequest.current) return;
    closeRequest.current = true;
    setClosing(true); setCloseError("");
    try { if (!onBeforeClose || await onBeforeClose()) setOpen(false); }
    catch (cause) { setCloseError(cause instanceof Error ? cause.message : String(cause)); }
    finally { closeRequest.current = false; setClosing(false); }
  };
  return <section ref={section} aria-label={title} className="settings-feature">
    <Card><Card.Content className="settings-feature-row"><h3>{title}</h3>
      {children && <Button variant="secondary" onPress={() => setOpen(true)}>{t("settings.configure")}</Button>}
      <ToggleField labelHidden label={title} selected={enabled} disabled={disabled} onChange={next => { setOpen(next); onChange(next); }} />
    </Card.Content></Card>
    {error && !open && <Alert status="danger" role="alert"><Alert.Description>{error}</Alert.Description></Alert>}
    {children && <Modal.Backdrop isOpen={open} onOpenChange={next => { if (!next) void close(); }} isDismissable={!closing} isKeyboardDismissDisabled={closing}>
      <Modal.Container size="lg"><Modal.Dialog className="settings-feature-dialog">
        <Modal.Header><Modal.Heading>{title}</Modal.Heading><Modal.CloseTrigger isDisabled={closing} /></Modal.Header>
        <Modal.Body>{children}{closeError && <Alert status="danger" role="alert"><Alert.Description>{closeError}</Alert.Description></Alert>}</Modal.Body>
      </Modal.Dialog></Modal.Container>
    </Modal.Backdrop>}
  </section>;
}
