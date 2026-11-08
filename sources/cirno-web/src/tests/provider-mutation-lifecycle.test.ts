import { act, cleanup, renderHook } from "@testing-library/react";
import { useTranslation } from "react-i18next";
import { afterEach, expect, it, vi } from "vitest";
import { createProviderMutations } from "@/features/settings/providers/actions/createProviderMutations";
import { useModelSettingsState } from "@/features/settings/models/useModelSettingsState";
import type { ModelSettingsActionsOptions } from "@/features/settings/modelOperations";
import type { CirnoClient } from "@/lib/cirno-client";
import { settingsPayload } from "./settings-test-utils";

afterEach(cleanup);
function setup() {
  const settings = settingsPayload();
  settings.providers = [
    {
      id: "bedrock",
      name: "Bedrock",
      configured: true,
      auth_type: "oauth",
      advanced_fields: ["region", "profile"],
    },
  ];
  const requestMutation = vi.fn().mockResolvedValue({ ...settings, requires_restart: true });
  const installCapabilities = vi.fn().mockResolvedValue(true);
  const setPendingRestartSections = vi.fn();
  const applyPayload = vi.fn();
  const setError = vi.fn();
  const { result } = renderHook(() => {
    const state = useModelSettingsState(settings);
    const { t } = useTranslation();
    const options: ModelSettingsActionsOptions = {
      state,
      settings,
      client: { requestMutation } as unknown as CirnoClient,
      t,
      applyPayload,
      setPendingRestartSections,
      setError,
      installCapabilities,
      onModelNameChange: vi.fn(),
      providerBusy: false,
      configuredModelProviderOptions: [],
    };
    return { state, ...createProviderMutations(options) };
  });
  return {
    result,
    settings,
    requestMutation,
    installCapabilities,
    setPendingRestartSections,
    applyPayload,
    setError,
  };
}

it("marks runtime restart after installing and saving an optional provider", async () => {
  const { result, requestMutation, installCapabilities, setPendingRestartSections, applyPayload } =
    setup();
  await act(async () => {
    expect(await result.current.saveProvider("bedrock")).toBe(true);
  });
  expect(installCapabilities).toHaveBeenCalledWith(["bedrock"]);
  expect(requestMutation).toHaveBeenCalledWith(
    "settings.provider.update",
    expect.objectContaining({ provider: "bedrock" }),
    20_000,
  );
  expect(setPendingRestartSections).toHaveBeenCalledTimes(1);
  const update = setPendingRestartSections.mock.calls[0][0];
  expect(update({ runtime: false, browser: true })).toEqual({
    runtime: true,
    browser: true,
  });
  expect(applyPayload).toHaveBeenCalledTimes(1);
  expect(result.current.state.providerSaving).toBeNull();
});

it("leaves settings untouched when optional support installation fails", async () => {
  const { result, requestMutation, installCapabilities, setPendingRestartSections } = setup();
  installCapabilities.mockResolvedValueOnce(false);
  await act(async () => {
    expect(await result.current.saveProvider("bedrock")).toBe(false);
  });
  expect(requestMutation).not.toHaveBeenCalled();
  expect(setPendingRestartSections).not.toHaveBeenCalled();
  expect(result.current.state.providerSaving).toBeNull();
});

it("reports a failed provider update without discarding its draft", async () => {
  const { result, requestMutation, setError, applyPayload } = setup();
  requestMutation.mockRejectedValueOnce(new Error("Provider unavailable"));
  await act(async () => {
    expect(await result.current.saveProvider("bedrock")).toBe(false);
  });
  expect(setError).toHaveBeenCalledWith("Provider unavailable");
  expect(applyPayload).not.toHaveBeenCalled();
  expect(result.current.state.providerSaving).toBeNull();
});
