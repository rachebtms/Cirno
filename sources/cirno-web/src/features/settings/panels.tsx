import { SettingsSectionSkeleton } from "@/features/settings/shared/SettingsSectionSkeleton";
import type { ComponentType } from "react";
import { lazy, Suspense } from "react";
import type { SettingsPanelProps } from "./contributions";

const Account = lazy(() => import("@/features/settings/account/AccountSettings").then(module => ({ default: module.AccountSettings })));
const About = lazy(() => import("@/features/settings/overview/OverviewSettings").then(module => ({ default: module.AboutSettings })));
const Backup = lazy(() => import("@/features/settings/system/BackupSettings").then(module => ({ default: module.BackupSettings })));
const Nodes = lazy(() => import("@/features/settings/nodes/NodesSettings").then(module => ({ default: module.NodesSettings })));

export const settingsPanels: Readonly<Record<string, ComponentType<SettingsPanelProps>>> = {
  account: function AccountPanel() { return <Account />; },
  about: function AboutPanel({ settings }) { return <About settings={settings} />; },
  backup: function BackupPanel({ client, onRestart }) { return <Backup client={client} onRestart={onRestart} />; },
  nodes: function NodesPanel({ client }) { return <Nodes client={client} />; },
};
export function SettingsModulePanel({ Panel, ...props }: SettingsPanelProps & { Panel: ComponentType<SettingsPanelProps> }) {
  return <Suspense fallback={<SettingsSectionSkeleton section="overview" />}><Panel {...props} /></Suspense>;
}
