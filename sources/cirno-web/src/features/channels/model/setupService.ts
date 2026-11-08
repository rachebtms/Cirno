import type { WebUIMutationTransport } from "@/lib/api";
import {
  configureChannel,
  validateChannel,
  disableCirnoFeature,
} from "@/lib/api";
export function createChannelSetupService(
  client: WebUIMutationTransport,
  name: string,
) {
  return {
    configure: (values: Record<string, string | null>, enable?: boolean) =>
      configureChannel(client, name, values, { enable }),
    validate: (values: Record<string, string | null>) =>
      validateChannel(client, name, values),
    disable: () => disableCirnoFeature(client, name),
  };
}
export type ChannelSetupService = ReturnType<typeof createChannelSetupService>;
