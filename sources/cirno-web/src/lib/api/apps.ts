/** Apps operations for the versioned Cirno API. */

import type { CliAppsPayload } from "@/lib/contracts/apps";
import {
  API_MUTATION_TIMEOUT_MS,
  API_READ_TIMEOUT_MS,
  PACKAGE_MUTATION_TIMEOUT_MS,
  mutation,
  request,
} from "./transport";
import type { CirnoFeaturesPayload } from "@/lib/contracts/channels";
import type { WebUIMutationTransport } from "./transport";

export async function fetchCliApps(
  token: string,
  base: string = "",
): Promise<CliAppsPayload> {
  return request<CliAppsPayload>(
    `${base}/v0/settings/cli-apps`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function fetchInstalledCliApps(
  token: string,
  base: string = "",
): Promise<CliAppsPayload> {
  return request<CliAppsPayload>(
    `${base}/v0/settings/cli-apps?installed_only=1`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function fetchCirnoFeatures(
  token: string,
  base: string = "",
): Promise<CirnoFeaturesPayload> {
  return request<CirnoFeaturesPayload>(
    `${base}/v0/settings/cirno-features`,
    token,
    undefined,
    API_READ_TIMEOUT_MS,
  );
}

export async function enableCirnoFeature(
  transport: WebUIMutationTransport,
  name: string,
  options: { instanceId?: string; installOnly?: boolean } = {},
): Promise<CirnoFeaturesPayload> {
  return mutation<CirnoFeaturesPayload>(
    transport,
    "settings.feature.enable",
    {
      name,
      ...(options.instanceId ? { instance_id: options.instanceId } : {}),
      ...(options.installOnly ? { install_only: true } : {}),
    },
    PACKAGE_MUTATION_TIMEOUT_MS,
  );
}

export async function disableCirnoFeature(
  transport: WebUIMutationTransport,
  name: string,
  options: { instanceId?: string } = {},
): Promise<CirnoFeaturesPayload> {
  return mutation<CirnoFeaturesPayload>(transport, "settings.feature.disable", {
    name,
    ...(options.instanceId ? { instance_id: options.instanceId } : {}),
  });
}

export async function runCliAppAction(
  transport: WebUIMutationTransport,
  action: "install" | "update" | "uninstall" | "test",
  name: string,
): Promise<CliAppsPayload> {
  return mutation<CliAppsPayload>(
    transport,
    `settings.cli_app.${action}`,
    { name },
    action === "install" || action === "update"
      ? PACKAGE_MUTATION_TIMEOUT_MS
      : API_MUTATION_TIMEOUT_MS,
  );
}
