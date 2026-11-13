import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { FixedSkillsSettings } from "@/features/settings/runtime/FixedSkillsSettings";
import { useRuntimeConfigSettings } from "@/features/settings/runtime/useRuntimeConfiguration";
import type { CirnoClient } from "@/lib/cirno-client";
import { installSettingsViewTestHooks, settingsPayload } from "./settings-test-utils";
installSettingsViewTestHooks();

it("saves fixed Skills through settings while preserving dependency and author declarations", async () => {
  const mutate = vi.fn(async (_method, payload) => ({ ...settingsPayload(), runtime_config: payload.values }));
  const client = { requestMutation: mutate } as unknown as CirnoClient;
  function Harness() {
    const [settings, setSettings] = useState({ ...settingsPayload(), runtime_config: { "agents.defaults.always_skills": ["removed"] } });
    const state = useRuntimeConfigSettings(settings, client, setSettings);
    return <FixedSkillsSettings state={state} loading={false} skills={[
      { name: "chosen", description: "Available", source: "home", available: true },
      { name: "missing-dependency", description: "Unavailable", source: "home", available: false },
      { name: "declared", description: "Skill declares always", source: "home", available: true, always: true },
    ]} />;
  }
  render(<Harness />);
  expect(screen.getByRole("checkbox", { name: /declared/ })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: /declared/ })).toBeDisabled();
  expect(screen.getByRole("checkbox", { name: /missing-dependency/ })).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox", { name: /chosen/ }));
  await waitFor(() => expect(mutate).toHaveBeenCalledWith("settings.runtime_config.update", { values: { "agents.defaults.always_skills": ["removed", "chosen"] } }, 20_000));
  await waitFor(() => expect(screen.getByRole("checkbox", { name: /removed/ })).toBeEnabled());
  fireEvent.click(screen.getByRole("checkbox", { name: /removed/ }));
  await waitFor(() => expect(mutate).toHaveBeenLastCalledWith("settings.runtime_config.update", { values: { "agents.defaults.always_skills": ["chosen"] } }, 20_000));
});
