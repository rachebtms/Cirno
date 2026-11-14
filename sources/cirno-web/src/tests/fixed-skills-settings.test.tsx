import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { skillInjectionSettings } from "@/features/settings/runtime/skill-injection";
import { useRuntimeConfigSettings } from "@/features/settings/runtime/useRuntimeConfiguration";
import { SkillsLibrary } from "@/features/skills/SkillsLibrary";
import type { CirnoClient } from "@/lib/cirno-client";
import type { SettingsPayload } from "@/lib/contracts/settings";
import { ClientProvider } from "@/providers/ClientProvider";
import { installSettingsViewTestHooks, jsonResponse, settingsPayload } from "./settings-test-utils";
installSettingsViewTestHooks();

const skills = [
  { name: "chosen", description: "Available", source: "home", available: true },
  { name: "missing-dependency", description: "Unavailable", source: "home", available: false },
  { name: "declared", description: "Skill declares always", source: "home", available: true, always: true },
];

function renderSkills(selected = ["removed"]) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const name = String(input).split("/").at(-1);
    return jsonResponse({ ...skills.find(item => item.name === name), enabled: true,
      raw_markdown: "Skill instructions", requirements: { bins: [], env: [], missing_bins: [], missing_env: [] }, install_options: [] });
  }));
  const mutate = vi.fn(async (_method, payload) => ({ ...settingsPayload(), runtime_config: payload.values }));
  const client = { requestMutation: mutate } as unknown as CirnoClient;
  function Harness() {
    const [settings, setSettings] = useState<SettingsPayload>({ ...settingsPayload(), runtime_config: { "agents.defaults.always_skills": selected } });
    const state = useRuntimeConfigSettings(settings, client, setSettings);
    return <ClientProvider client={client} token="fixture">
      <SkillsLibrary skills={skills} injection={skillInjectionSettings(state)} />
    </ClientProvider>;
  }
  render(<Harness />);
  return mutate;
}

it("offers fixed injection inside Skill details and preserves other selections when autosaving", async () => {
  const mutate = renderSkills();
  expect(screen.queryByRole("heading", { name: "Fixed Skills" })).not.toBeInTheDocument();
  expect(screen.queryByRole("switch", { name: "Always inject" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Open details for chosen" }));
  const toggle = await screen.findByRole("switch", { name: "Always inject" });
  fireEvent.click(toggle);
  await waitFor(() => expect(mutate).toHaveBeenCalledWith("settings.runtime_config.update", {
    values: { "agents.defaults.always_skills": ["removed", "chosen"] },
  }, 20_000));
  await waitFor(() => expect(toggle).toBeEnabled());
  expect(toggle).toBeChecked();
  fireEvent.click(toggle);
  await waitFor(() => expect(mutate).toHaveBeenLastCalledWith("settings.runtime_config.update", {
    values: { "agents.defaults.always_skills": ["removed"] },
  }, 20_000));
});

it.each([
  ["declared", [], true, true],
  ["missing-dependency", [], false, true],
  ["missing-dependency", ["missing-dependency"], true, false],
] as const)("preserves declaration and availability rules for %s", async (name, selection, checked, disabled) => {
  renderSkills([...selection]);
  fireEvent.click(screen.getByRole("button", { name: `Open details for ${name}` }));
  const toggle = await screen.findByRole("switch", { name: "Always inject" });
  if (checked) expect(toggle).toBeChecked();
  else expect(toggle).not.toBeChecked();
  if (disabled) expect(toggle).toBeDisabled();
  else expect(toggle).toBeEnabled();
});

it("shows save failures inside details and retries without introducing a Save button", async () => {
  const mutate = renderSkills();
  mutate.mockRejectedValueOnce(new Error("Could not save injection setting"));
  fireEvent.click(screen.getByRole("button", { name: "Open details for chosen" }));
  fireEvent.click(await screen.findByRole("switch", { name: "Always inject" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not save injection setting");
  expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(mutate).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(screen.getByRole("switch", { name: "Always inject" })).toBeChecked();
});

it("keeps activation errors visible after the injection preference has saved", async () => {
  const mutate = renderSkills();
  fireEvent.click(screen.getByRole("button", { name: "Open details for chosen" }));
  const injection = await screen.findByRole("switch", { name: "Always inject" });
  fireEvent.click(injection);
  await waitFor(() => expect(mutate).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(injection).toBeEnabled());
  mutate.mockRejectedValueOnce(new Error("Skill activation update failed"));
  fireEvent.click(screen.getByRole("switch", { name: "Use skill" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Skill activation update failed");
});
