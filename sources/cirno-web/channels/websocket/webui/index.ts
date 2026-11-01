import type { ChannelUiContribution } from "@/channel-plugins/types";
import { chatAppGuideUrl } from "@/channel-plugins/catalog";

import { WebSocketIcon } from "./WebSocketIcon";

export default {
  presentation: {
    displayName: "Cirno Web",
    initials: "WS",
    color: "#111827",
    icon: WebSocketIcon,
    setup: {
      mode: "credentials",
      docsUrl: chatAppGuideUrl("websocket"),
    },
  },
} satisfies ChannelUiContribution;
