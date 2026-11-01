import { describe, expect, it } from "vitest";
import { channelUiContribution, channelUiOwner, channelUiPresentation, registeredChannelUiContributions } from "@/channel-plugins/registry";

describe("channel UI contributions", () => {
  it("only bundles Telegram and Web contributions and checks the backend entry", () => {
    expect(registeredChannelUiContributions().map(entry => entry.channel).sort()).toEqual(["telegram", "websocket"]);
    expect(channelUiContribution("telegram", "webui/index.ts")?.presentation.displayName).toBe("Telegram");
    expect(channelUiContribution("telegram", undefined)).toBeUndefined();
    expect(channelUiContribution("telegram", "webui/missing.tsx")).toBeUndefined();
    expect(channelUiContribution("missing", "webui/index.ts")).toBeUndefined();
    expect(channelUiContribution("websocket", "webui/index.ts")?.presentation.icon).toBeDefined();
  });
  it("does not redirect unknown channels to a bundled channel", () => {
    expect(channelUiOwner("telegram")).toBe("telegram");
    expect(channelUiPresentation("websocket")?.displayName).toBe("Cirno Web");
    expect(channelUiPresentation("removed-channel")).toBeUndefined();
    expect(channelUiOwner("removed-channel")).toBe("removed-channel");
  });
});
