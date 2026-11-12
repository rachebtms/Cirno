import { Alert, Skeleton } from "@heroui/react";
import { SkeletonStatus } from "@/ui/feedback/SkeletonStatus";
import type { ReactNode } from "react";
import { DialogLayoutContext } from "@/components/ui/dialog";
import { SharedProxySetupDialog } from "./shared/SharedProxySetupDialog";
import { SettingsLayout } from "./ui/SettingsLayout";
import { RestartExitDialog } from "./ui/RestartExitDialog";
import { SettingsNavigation, standaloneSectionTitle } from "./ui/SettingsNavigation";
import { settingsSections } from "./modules";
import { SettingsModulePanel } from "./panels";
import type { SettingsSectionKey } from "./contracts";
import type { SettingsPageProps } from "./composition/contracts";
import { SettingsOverlays } from "./composition/SettingsOverlays";
import { useSettingsComposition } from "./composition/useSettingsComposition";
import { createModelSections } from "./composition/ModelSections";
import { createRuntimeSections } from "./composition/RuntimeSections";
import { createPersonalSections } from "./composition/PersonalSections";
import { createChannelSections } from "./composition/ChannelSections";
import { createAppSections } from "./composition/AppSections";
import { createAutomationSections } from "./composition/AutomationSections";

export function SettingsPage(props: SettingsPageProps) {
  const bindings = useSettingsComposition(props);
  const { dialogLayoutAnchor, setDialogLayoutAnchor, controller, showSidebar, activeSection, selectSection, onLogout, requestExit, settings, restartViaSettingsSurface, restartInProgress, hideHeader, t, pendingExit, setPendingExit, presetDeletedCallback, setAutomationDetailReturn, loading, error, proxySetupOpen, setProxySetupOpen } = bindings;
  const sections = {
    ...createModelSections(bindings),
    ...createRuntimeSections(bindings),
    ...createPersonalSections(bindings),
    ...createChannelSections(bindings),
    ...createAppSections(bindings),
    ...createAutomationSections(bindings),
  };
  const renderSection = (section: SettingsSectionKey, embedded = false): ReactNode => {
    const Panel = settingsSections.get(section)?.Panel;
    if (Panel && settings) return <SettingsModulePanel Panel={Panel} client={controller.client} settings={settings}
      onRestart={restartViaSettingsSurface} selectSection={selectSection} />;
    return sections[section]?.({ embedded }) ?? null;
  };
  // Display sections read server-synchronized owner preferences independently of service settings.
  const ownerSection = ["appearance", "reading", "activity", "notifications"].includes(activeSection);
  const sectionReady = ownerSection || settings !== null || activeSection === "skills" || activeSection === "apps"
    || activeSection === "channels" || activeSection === "telegram" || activeSection === "automations";

  return (
    <DialogLayoutContext.Provider value={dialogLayoutAnchor}>
      <SettingsLayout navigation={showSidebar ? (
        <SettingsNavigation
          activeSection={activeSection}
          onSelectSection={selectSection}
          onLogout={onLogout ? () => requestExit(onLogout) : undefined}

          onRestart={settings ? restartViaSettingsSurface : undefined}
          isRestarting={restartInProgress}
          restartPending={settings?.requires_restart}

        />
      ) : undefined} section={activeSection} title={hideHeader ? undefined : t(`settings.nav.${activeSection}`, { defaultValue: standaloneSectionTitle(activeSection) })}
        contentRef={setDialogLayoutAnchor} overlays={<>
          <RestartExitDialog leave={pendingExit} onClose={() => setPendingExit(null)} onRestart={() => { void restartViaSettingsSurface(); }} />
          <SettingsOverlays controller={controller} presetDeletedCallback={presetDeletedCallback} onAutomationReturn={setAutomationDetailReturn} />


        </>}>
        {loading && !sectionReady ? <SkeletonStatus className="settings-loading" label={t("settings.status.loading")}><Skeleton /><Skeleton /><Skeleton /></SkeletonStatus>
          : error && !sectionReady ? <Alert status="danger" role="alert"><Alert.Content>{error}</Alert.Content></Alert>
            : sectionReady ? <>
              {error && (!ownerSection || settings !== null) && <Alert status="danger" role="alert"><Alert.Content>{error}</Alert.Content></Alert>}
              {renderSection(activeSection)}
            </> : null}
      </SettingsLayout>
      {proxySetupOpen ? <SharedProxySetupDialog
        busy={controller.runtimeConfigState.saving !== null}
        onClose={() => setProxySetupOpen(false)}
        onSave={controller.runtimeConfigState.saveProxy}
      /> : null}
    </DialogLayoutContext.Provider>
  );
}
