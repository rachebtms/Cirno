import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";
import type { CirnoFeatureInfo } from "@/lib/contracts/channels";
import { ChannelCard } from "@/features/channels/ui/ChannelCard";
import { ChannelInstances } from "@/features/channels/ChannelInstances";

const base: CirnoFeatureInfo = {
  name: "fixture", display_name: "Fixture", type: "channel", enabled: false,
  installed: true, configured: false, ready: false, status: "failed",
  runtime_status: "failed", running: true, install_supported: true, requires_restart: false,
};

it.each([false, true])("allows stopping an active channel while restart is pending (support=%s)", (support) => {
  const onAction = vi.fn(async () => {});
  render(<ChannelCard feature={{ ...base, restart_pending: support }} showBrandLogos={false}
    actionKey={null} restartRequired onSelect={vi.fn()} onAction={onAction} />);
  const toggle = screen.getByRole("switch", { name: "Fixture channel" });
  expect(toggle).toBeChecked();
  expect(toggle).toBeEnabled();
  fireEvent.click(toggle);
  expect(onAction).toHaveBeenCalledWith("disable", "fixture");
});

it("still blocks enabling an inactive channel before the pending restart", () => {
  render(<ChannelCard feature={{ ...base, runtime_status: "stopped", running: false }} showBrandLogos={false}
    actionKey={null} restartRequired onSelect={vi.fn()} onAction={vi.fn(async () => {})} />);
  expect(screen.getByRole("switch")).not.toBeChecked();
  expect(screen.getByRole("switch")).toBeDisabled();
});

it("allows stopping an already loaded adapter even if its dependency is unavailable", () => {
  const onAction = vi.fn(async () => {});
  render(<ChannelCard feature={{ ...base, installed: false }} showBrandLogos={false}
    actionKey={null} onSelect={vi.fn()} onAction={onAction} />);
  fireEvent.click(screen.getByRole("switch"));
  expect(onAction).toHaveBeenCalledWith("disable", "fixture");
});

it("keeps the required WebUI channel stop guard", () => {
  render(<ChannelCard feature={{ ...base, capabilities: ["always_enabled"] }} showBrandLogos={false}
    actionKey={null} onSelect={vi.fn()} onAction={vi.fn(async () => {})} />);
  expect(screen.getByRole("switch")).toBeDisabled();
});

it("does not inherit parent running state when an older instance payload omits its flag", () => {
  const client = { requestMutation: vi.fn() } as unknown as CirnoClient;
  render(<ClientProvider client={client} token="fixture">
    <ChannelInstances feature={{ ...base, running: true, instances: [{
      id: "idle", name: "Idle", enabled: false, configured: true,
      runtime_status: "stopped", config_values: {}, configured_fields: [],
    }] }} showBrandLogos={false} onFeaturesUpdate={vi.fn()} />
  </ClientProvider>);
  expect(screen.getByText("Ready")).toBeVisible();
  expect(screen.getByRole("switch")).not.toBeChecked();
});

it.each([true, false])("only requires instance credentials when enabling, not stopping (live=%s)", async (live) => {
  const requestMutation = vi.fn(async () => ({ features: [], enabled_count: 0 }));
  const client = { requestMutation } as unknown as CirnoClient;
  const feature = { ...base, instances: [{
    id: "worker", name: "Worker", enabled: false, configured: false,
    runtime_status: live ? "failed" : "stopped", running: live,
    config_values: {}, configured_fields: [],
  }] };
  render(<ClientProvider client={client} token="fixture">
    <ChannelInstances feature={feature} showBrandLogos={false} onFeaturesUpdate={vi.fn()} />
  </ClientProvider>);
  const toggle = screen.getByRole("switch", { name: "Worker instance" });
  if (live) {
    expect(toggle).toBeChecked();
    expect(toggle).toBeEnabled();
    await act(async () => { fireEvent.click(toggle); });
    expect(requestMutation).toHaveBeenCalledWith("settings.feature.disable", { name: "fixture", instance_id: "worker" }, expect.any(Number));
  } else {
    expect(toggle).not.toBeChecked();
    expect(toggle).toBeDisabled();
    expect(requestMutation).not.toHaveBeenCalled();
  }
});
