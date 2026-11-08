import type { CirnoFeatureInfo } from "@/lib/contracts/channels";
export function channelIsRunning(
  feature: Pick<CirnoFeatureInfo, "runtime_status">,
): boolean {
  return feature.runtime_status === "running";
}

export function channelToggleChecked(
  feature: Pick<CirnoFeatureInfo, "runtime_status">,
): boolean {
  return (
    feature.runtime_status === "running" ||
    feature.runtime_status === "starting"
  );
}

export function channelStatusLabel(
  feature: CirnoFeatureInfo,
  tx: (key: string, fallback: string) => string,
): string {
  if (feature.runtime_status === "failed") {
    return tx("settings.channels.runtimeFailed", "Failed");
  }
  if (feature.runtime_status === "starting") {
    return tx("settings.channels.runtimeStarting", "Starting");
  }
  if (channelIsRunning(feature)) return tx("settings.values.on", "On");
  if (feature.enabled)
    return tx("settings.channels.runtimeStopped", "Not running");
  if (feature.configured === false)
    return tx("settings.channels.needsConfig", "Needs setup");
  if (feature.configured === true)
    return tx("settings.cirnoFeatures.ready", "Ready");
  return tx("settings.values.off", "Off");
}
