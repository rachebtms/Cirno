import { Alert, Button, Spinner } from "@heroui/react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { SettingsPayload } from "@/lib/contracts/settings";
import type { RuntimeConfigPage } from "../system/runtime-config-fields";
import { ConfigurationField } from "./fields";
import { configurationGroups } from "./model";
import type { RuntimeConfigController } from "./useRuntimeConfiguration";
import "./configuration.css";

export function RuntimeConfiguration({ page, settings, state, onRestart, isRestarting, children }: {
  page: RuntimeConfigPage;
  settings: SettingsPayload;
  state: RuntimeConfigController;
  onRestart?: () => void;
  isRestarting: boolean;
  children?: ReactNode;
}) {
  const { t } = useTranslation();
  const tr = (key: string) => t(`settings.runtimeConfig.${key}`);
  if (!settings.runtime_config) return <div className="configuration-page"><Alert status="warning"><Alert.Content>{tr("unavailable")}</Alert.Content></Alert>{children}</div>;
  return <div className="configuration-page">
    {settings.requires_restart && onRestart && <Alert status="warning"><Alert.Content>{t("settings.status.savedRestartApply")}</Alert.Content>
      <Button size="sm" variant="secondary" onPress={onRestart} isPending={isRestarting}>{t("app.system.restartAction")}</Button>
    </Alert>}
    {configurationGroups(page).map(group => {
      if (group.enabledBy && state.value(group.enabledBy) === false) return null;
      if (group.id === "chat") return <div key={group.id}>{children}</div>;
      const fields = group.fields.filter(state.visible);
      const dirty = fields.some(state.dirty);
      const saving = state.saving === group.id;
      const showActions = dirty && !saving && !!state.errors[group.id];
      const title = group.id === "memory" && page !== "memory" ? t(`settings.nav.${page}`) : tr(`groups.${group.id}.title`);
      return <section key={group.id} aria-label={title} className="configuration-section">
        {title !== t(`settings.nav.${page}`) && <h2>{title}</h2>}
        {group.id === "approval" && <p className="configuration-help">{tr("groups.approval.help")}</p>}
        <form noValidate onSubmit={event => { event.preventDefault(); void state.save(group.id); }}
          onBlur={event => {
            if (!event.currentTarget.contains(event.relatedTarget) && !state.errors[group.id]
              && fields.some(field => field.saveOnBlur && state.dirty(field))) void state.save(group.id);
          }}>
          {/* Preserve native Enter submission without exposing a manual save action. */}
          <button type="submit" hidden />
          <fieldset disabled={isRestarting}>
            <legend className="sr-only">{title}</legend>
            {fields.map(field => <ConfigurationField key={field.path} field={field} settings={settings} state={state} disabled={isRestarting} />)}
          </fieldset>
          <footer className="configuration-save">
            <span role="status">{saving ? <Spinner size="sm" /> : !dirty && state.saved[group.id] ? tr("saved") : null}</span>
            {showActions && <><Button type="button" variant="tertiary" size="sm" onPress={() => state.discard(group.id)} isDisabled={saving || isRestarting}>{t("common.cancel")}</Button>
              <Button type="submit" size="sm" isPending={saving} isDisabled={isRestarting}>{t("common.retry")}</Button></>}
          </footer>
          {state.errors[group.id] && <Alert status="danger" role="alert"><Alert.Content>{state.errors[group.id]}</Alert.Content></Alert>}
        </form>
      </section>;
    })}
  </div>;
}
