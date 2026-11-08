/** Channels operations for the versioned Cirno API. */

import type {
  ChannelConfigurePayload,
  ChannelConnectPayload,
  ChannelValidationPayload,
} from "@/lib/contracts/channels";
import {
  PACKAGE_MUTATION_TIMEOUT_MS,
  mutation,
} from "./transport";
import type { WebUIMutationTransport } from "./transport";

export async function startChannelConnect<T = ChannelConnectPayload>(
  transport: WebUIMutationTransport,
  channel: string,
  params: Readonly<Record<string, string | boolean>> = {},
): Promise<T> {
  return mutation<T>(
    transport,
    "settings.channel.connect.start",
    {
      ...params,
      channel,
    },
    PACKAGE_MUTATION_TIMEOUT_MS,
  );
}

export async function pollChannelConnect(
  transport: WebUIMutationTransport,
  channel: string,
  sessionId: string,
  params: Readonly<Record<string, string>> = {},
): Promise<ChannelConnectPayload> {
  const values = Object.fromEntries(
    Object.entries(params).filter(([key]) => key !== "session_id"),
  );
  return mutation<ChannelConnectPayload>(
    transport,
    "settings.channel.connect.poll",
    { channel, session_id: sessionId, ...values },
    PACKAGE_MUTATION_TIMEOUT_MS,
  );
}

export async function cancelChannelConnect(
  transport: WebUIMutationTransport,
  channel: string,
  sessionId: string,
): Promise<ChannelConnectPayload> {
  return mutation<ChannelConnectPayload>(
    transport,
    "settings.channel.connect.cancel",
    { channel, session_id: sessionId },
  );
}

export async function configureChannel(
  transport: WebUIMutationTransport,
  name: string,
  values: Record<string, string | null>,
  options: { enable?: boolean; instanceId?: string } = {},
): Promise<ChannelConfigurePayload> {
  return mutation<ChannelConfigurePayload>(
    transport,
    "settings.channel.configure",
    {
      name,
      values,
      ...(options.enable !== undefined ? { enable: options.enable } : {}),
      ...(options.instanceId ? { instance_id: options.instanceId } : {}),
    },
    PACKAGE_MUTATION_TIMEOUT_MS,
  );
}

export async function validateChannel(
  transport: WebUIMutationTransport,
  name: string,
  values: Record<string, string | null> = {},
  options: { instanceId?: string } = {},
): Promise<ChannelValidationPayload> {
  return mutation<ChannelValidationPayload>(
    transport,
    "settings.channel.validate",
    {
      name,
      values,
      ...(options.instanceId ? { instance_id: options.instanceId } : {}),
    },
  );
}
