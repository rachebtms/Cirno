import { Alert, Button, Form, Modal } from "@heroui/react";
import { RefreshCw, Wallet } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { useProviderBalance } from "./model/useProviderBalance";
import { ProviderBalanceFields } from "./ProviderBalanceFields";
export function ProviderBalanceControl({ provider, onSaved }: { provider: SettingsPayload["providers"][number]; onSaved: (settings: SettingsPayload) => void }) {
  const { t } = useTranslation();
  const model = useProviderBalance(provider, onSaved);
  return <div className="provider-balance"><div className="provider-balance-actions">
    <Button variant="ghost" size="sm" aria-label={`${t("settings.balance.title")}: ${provider.name}`} onPress={model.edit}><Wallet size={16} />{t("settings.balance.title")}</Button>
    {provider.balance && <Button isIconOnly variant="ghost" size="sm" isPending={model.loading} aria-label={`${t("settings.balance.refresh")}: ${provider.name}`} onPress={() => void model.refresh()}><RefreshCw size={16} /></Button>}
    {model.balances.map(balance => <span key={balance.currency}>{balance.amount} {balance.currency}</span>)}
  </div>{model.error && !model.open && <Alert status="danger" role="alert"><Alert.Description>{model.error}</Alert.Description></Alert>}
    <Modal.Backdrop isOpen={model.open} onOpenChange={open => { if (!model.saving) model.setOpen(open); }} isDismissable={!model.saving} isKeyboardDismissDisabled={model.saving}><Modal.Container size="sm"><Modal.Dialog>
        <Modal.Header><Modal.Heading>{t("settings.balance.title")}</Modal.Heading><p className="provider-secondary">{provider.name}</p></Modal.Header>
        <Form onSubmit={event => { event.preventDefault(); void model.save(); }}><Modal.Body><ProviderBalanceFields value={model.draft} providerId={provider.id} onChange={model.setDraft} />
          {model.error && <Alert status="danger" role="alert"><Alert.Description>{model.error}</Alert.Description></Alert>}
        </Modal.Body><Modal.Footer><Button variant="secondary" isDisabled={model.saving} onPress={() => model.setOpen(false)}>{t("settings.actions.cancel")}</Button>
          <Button type="submit" isPending={model.saving} isDisabled={model.draft !== null && !model.draft.endpoint.trim()}>{t("settings.actions.save")}</Button></Modal.Footer></Form>
      </Modal.Dialog></Modal.Container></Modal.Backdrop>
  </div>;
}
