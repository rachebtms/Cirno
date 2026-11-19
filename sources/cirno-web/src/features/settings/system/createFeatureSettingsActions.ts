import type { SystemSettingsState } from "./useSystemSettingsState";
import type { CirnoClient } from "@/lib/cirno-client";
import { createSettingsActionGate } from "./createSettingsActionGate";
import type { Dispatch, SetStateAction } from "react";
import type { PendingRestartSections } from "@/features/settings/contracts";
import type { CirnoFeatureInfo } from "@/lib/contracts/channels";
import { disableCirnoFeature, enableCirnoFeature } from "@/lib/api";

interface Options {
  state: SystemSettingsState;
  client: CirnoClient;
  featureCatalog: CirnoFeatureInfo[];
  setPendingRestartSections: Dispatch<SetStateAction<PendingRestartSections>>;
}

export function createFeatureSettingsActions({ state, client, featureCatalog, setPendingRestartSections }: Options) {
  const { isSystemSettingsCurrent, cirnoFeatureActionRef, cirnoFeaturesRevisionRef,
    setCirnoFeatureAction, setCirnoFeaturesLoading, setCirnoFeaturesError,
    setCirnoFeatureConfirm, publishCirnoFeatures } = state;
  const { begin: beginCirnoFeatureAction, end: endCirnoFeatureAction } = createSettingsActionGate({
    isCurrent: isSystemSettingsCurrent, actionRef: cirnoFeatureActionRef, revisionRef: cirnoFeaturesRevisionRef,
    setAction: setCirnoFeatureAction, setLoading: setCirnoFeaturesLoading,
  });

  const installCapabilities = async (names: string[]): Promise<boolean> => {
    if (!isSystemSettingsCurrent()) return false;
    const missing = names.filter(
      (name) => !featureCatalog.find((feature) => feature.name === name)?.installed,
    );
    if (!missing.length) return true;
    const key = `enable:${names.join("+")}`;
    if (!beginCirnoFeatureAction(key)) return false;
    setCirnoFeaturesError(null);
    try {
      for (const name of missing) {
        if (!isSystemSettingsCurrent()) return false;
        const latest = await enableCirnoFeature(client, name);
        if (!isSystemSettingsCurrent()) return false;
        publishCirnoFeatures(latest);
        if (latest.requires_restart) {
          setPendingRestartSections((prev) => ({ ...prev, runtime: true }));
        }
        if (latest.last_action?.ok === false) {
          setCirnoFeaturesError(latest.last_action.message);
          return false;
        }
      }
      return true;
    } catch (err) {
      if (isSystemSettingsCurrent()) setCirnoFeaturesError((err as Error).message);
      return false;
    } finally {
      endCirnoFeatureAction(key);
    }
  };

  const handleCirnoFeatureAction = async (
    action: "enable" | "disable",
    name: string,
    options: { confirmed?: boolean; installOnly?: boolean } = {},
  ) => {
    if (!isSystemSettingsCurrent()) return;
    const feature = featureCatalog.find((item) => item.name === name);
    if (
      action === "enable"
      && !options.confirmed
      && feature
      && !feature.installed
      && feature.install_supported
    ) {
      setCirnoFeaturesError(null);
      setCirnoFeatureConfirm({ feature, installOnly: Boolean(options.installOnly) });
      return;
    }
    const key = `${action === "enable" && options.installOnly ? "install" : action}:${name}`;
    if (!beginCirnoFeatureAction(key)) return;
    setCirnoFeatureConfirm(null);
    setCirnoFeaturesError(null);
    try {
      const payload = action === "enable"
        ? await enableCirnoFeature(client, name, { installOnly: options.installOnly })
        : await disableCirnoFeature(client, name);
      if (!isSystemSettingsCurrent()) return;
      publishCirnoFeatures(payload);
      if (payload.last_action?.ok === false) {
        setCirnoFeaturesError(payload.last_action.message);
      }
      if (payload.requires_restart) {
        setPendingRestartSections((prev) => ({ ...prev, runtime: true }));
      }
    } catch (err) {
      if (!isSystemSettingsCurrent()) return;
      console.error("cirno feature action failed", {
        action,
        name,
        installOnly: Boolean(options.installOnly),
        error: err,
      });
      setCirnoFeaturesError(err instanceof Error ? err.message : String(err));
    } finally {
      endCirnoFeatureAction(key);
    }
  };

  return { installCapabilities, handleCirnoFeatureAction };
}
