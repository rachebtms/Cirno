import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it, vi } from "vitest";
import { ModelCapabilityFields } from "@/features/settings/models/ui/ModelCapabilityFields";
import { agentDraftFromPayload, type AgentSettingsDraft } from "@/features/settings/models/modelDraft";
import { ClientProvider } from "@/providers/ClientProvider";
import type { CirnoClient } from "@/lib/cirno-client";
import type { CapabilityResults } from "@/features/settings/models/probeModelCapabilities";
import { settingsPayload } from "./settings-test-utils";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
const detected: CapabilityResults = {
  image: { supported: true, detail: "Image confirmed" },
  video: { supported: false, detail: "Video unavailable" },
};
function setup() {
  const requestMutation = vi.fn();
  const busy = vi.fn();
  const client = { requestMutation } as unknown as CirnoClient;
  function Harness({ visible, preset = "first" }: { visible: boolean; preset?: string }) {
    const [form, setForm] = useState<AgentSettingsDraft>(() => ({ ...agentDraftFromPayload(settingsPayload()), imageInput: null, videoInput: null }));
    return <ClientProvider client={client} token="fixture">
      <output data-testid="image">{String(form.imageInput)}</output>
      {visible && <ModelCapabilityFields key={preset} presetId={preset} form={form} setForm={setForm} disabled={false} onBusyChange={busy} />}
    </ClientProvider>;
  }
  const view = render(<Harness visible />);
  return { ...view, requestMutation, busy, show: (visible: boolean, preset = "first") => view.rerender(<Harness visible={visible} preset={preset} />) };
}
function start() { fireEvent.click(screen.getByRole("button", { name: /Test/ })); }

it("does not apply a retired capability probe to the shared model draft after leaving and reopening", async () => {
  const pending = deferred<CapabilityResults>();
  const view = setup();
  view.requestMutation.mockReturnValue(pending.promise);
  start();
  view.show(false);
  view.show(true, "second");
  await act(async () => { pending.resolve(detected); });
  expect(screen.getByTestId("image")).toHaveTextContent("null");
  expect(screen.queryByText("Image confirmed")).not.toBeInTheDocument();
});

it("releases the parent probe busy state when its fields unmount", () => {
  const view = setup();
  view.requestMutation.mockReturnValue(new Promise(() => {}));
  start();
  expect(view.busy).toHaveBeenLastCalledWith(true);
  view.show(false);
  expect(view.busy).toHaveBeenLastCalledWith(false);
});

it("still applies a current probe result and clears busy", async () => {
  const pending = deferred<CapabilityResults>();
  const view = setup();
  view.requestMutation.mockReturnValue(pending.promise);
  start();
  await act(async () => { pending.resolve(detected); });
  expect(screen.getByTestId("image")).toHaveTextContent("true");
  expect(screen.getByText("Image confirmed")).toBeVisible();
  expect(view.busy).toHaveBeenLastCalledWith(false);
  expect(view.requestMutation).toHaveBeenCalledTimes(1);
});

it("serializes repeated probe presses before React commits the busy indicator", async () => {
  const pending = deferred<CapabilityResults>();
  const view = setup();
  view.requestMutation.mockReturnValue(pending.promise);
  act(() => { start(); start(); });
  const admitted = view.requestMutation.mock.calls.length;
  await act(async () => { pending.resolve(detected); });
  expect(admitted).toBe(1);
});

it("shows a current probe failure and permits an explicit retry", async () => {
  const view = setup();
  view.requestMutation.mockRejectedValueOnce(new Error("Probe unavailable")).mockResolvedValueOnce(detected);
  await act(async () => { start(); });
  expect(screen.getByRole("alert")).toHaveTextContent("Probe unavailable");
  expect(view.busy).toHaveBeenLastCalledWith(false);
  await act(async () => { start(); });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByTestId("image")).toHaveTextContent("true");
  expect(view.requestMutation).toHaveBeenCalledTimes(2);
});
