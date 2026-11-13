import { Alert, Button, Spinner } from "@heroui/react";
import { CircleAlert, KeyRound, Plus, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { CirnoClient } from "@/lib/cirno-client";
import { useCredentialVault } from "./model/useCredentialVault";
import { CredentialEditor } from "./ui/CredentialEditor";
import { CredentialRecords } from "./ui/CredentialRecords";
import "./credentials.css";

export function CredentialsTab({ client, active, onDirtyChange }: {
  client: CirnoClient; active: boolean; onDirtyChange?: (dirty: boolean) => void;
}) {
  const { t } = useTranslation();
  const vault = useCredentialVault(client, active, onDirtyChange);
  return <section className="credential-screen">
    <div className="credential-page">
      <header><h1><KeyRound size={22} />{t("workspace.credentials")}</h1>
        <div className="credential-page-actions"><Button isIconOnly size="sm" variant="ghost" aria-label={t("features.refresh")} isDisabled={vault.busy || vault.loading} onPress={() => { void vault.refresh(); }}><RefreshCw size={16} /></Button>
        <Button size="sm" isDisabled={vault.busy || !!vault.draft?.modified} onPress={() => vault.begin()}><Plus size={16} />{t("workspace.addRecord")}</Button></div>
      </header>
      <p className="credential-hint">{t("workspace.vaultHint")}</p>
      {vault.error && <Alert status="danger" role="alert"><Alert.Indicator><CircleAlert /></Alert.Indicator>
        <Alert.Content><Alert.Description>{vault.error}</Alert.Description></Alert.Content>
      </Alert>}
      {vault.listError && <Alert status="danger" role="alert"><Alert.Indicator><CircleAlert /></Alert.Indicator>
        <Alert.Content><Alert.Description>{vault.listError}</Alert.Description></Alert.Content>
        <Button size="sm" variant="ghost" isDisabled={vault.busy} onPress={() => { void vault.refresh(); }}>{t("common.retry")}</Button>
      </Alert>}
      {vault.draft && <CredentialEditor visible={vault.secretVisible} toggleVisible={vault.toggleSecret} draft={vault.draft} busy={vault.busy} update={vault.update} cancel={vault.clear} reveal={vault.reveal} save={vault.save} scan={vault.scan} fingerprints={vault.fingerprints} loadSSH={vault.loadSSH} />}
      {vault.loading && !vault.records.length ? <Spinner aria-label={t("common.loading")} /> : vault.records.length ?
        <CredentialRecords records={vault.records} disabled={vault.busy || !!vault.draft?.modified} deleting={vault.deleting} confirm={vault.setDeleting} edit={vault.begin} remove={vault.remove} /> :
        !vault.listError && <p className="credential-empty">{t("workspace.noRecords")}</p>}
    </div>
  </section>;
}
