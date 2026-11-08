import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ChannelCard } from "@/features/channels/ui/ChannelCard";
import type { CirnoFeatureInfo } from "@/lib/contracts/channels";

it("opens Web connection settings while keeping its channel enabled", () => {
  const onSelect = vi.fn();
  const onAction = vi.fn();
  const feature = { name: "websocket", display_name: "Cirno Web", type: "channel", webui: "webui/index.ts",
    enabled: true, installed: true, ready: true, status: "enabled", capabilities: ["always_enabled"],
  } as CirnoFeatureInfo;
  render(<ChannelCard feature={feature} showBrandLogos onSelect={onSelect} actionKey={null} onAction={onAction} />);
  fireEvent.click(screen.getByRole("button", { name: "View Cirno Web settings" }));
  expect(onSelect).toHaveBeenCalledOnce();
  expect(screen.getByRole("switch", { name: "Cirno Web channel" })).toBeDisabled();
  expect(onAction).not.toHaveBeenCalled();
});
