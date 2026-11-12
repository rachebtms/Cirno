import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useRuntimeConfigSettings } from "@/features/settings/runtime/useRuntimeConfiguration";
import { RUNTIME_CONFIG_FIELDS } from "@/features/settings/system/runtime-config-fields";
import { settingsPayload } from "./settings-test-utils";
import type { CirnoClient } from "@/lib/cirno-client";
import type { SettingsPayload } from "@/lib/contracts/settings";

afterEach(cleanup);
it.each(["replace", "unmount"])("ignores an earlier settings acknowledgement after owner %s", async change => {
  let resolve!: (payload: SettingsPayload) => void;
  const request = vi.fn(() => new Promise<SettingsPayload>(done => { resolve = done; }));
  const first = { requestMutation: request } as unknown as CirnoClient;
  const second = { requestMutation: vi.fn() } as unknown as CirnoClient;
  const settings = { ...settingsPayload(), runtime_config: { "agents.defaults.max_tool_iterations": 200 } };
  const apply = vi.fn();
  const state = renderHook(({ client }) => useRuntimeConfigSettings(settings, client, apply), { initialProps: { client: first } });
  const field = RUNTIME_CONFIG_FIELDS.find(field => field.path === "agents.defaults.max_tool_iterations")!;
  let saved!: Promise<boolean>;
  act(() => { state.result.current.change(field, "37"); saved = state.result.current.save(field.group); });
  expect(request).toHaveBeenCalledOnce();
  if (change === "replace") state.rerender({ client: second });
  else state.unmount();
  await act(async () => {
    resolve({ ...settings, runtime_config: { "agents.defaults.max_tool_iterations": 37 } });
    await saved;
  });
  expect(apply).not.toHaveBeenCalled();
  expect(second.requestMutation).not.toHaveBeenCalled();
});
