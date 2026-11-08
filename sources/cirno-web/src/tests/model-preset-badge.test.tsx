import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ModelSelector } from "@/features/model-selection/ModelSelector";
const presets = [
  {
    id: "zhipu",
    name: "Zhipu",
    model: "glm-5",
    provider: "zhipu",
    contextWindowTokens: 1000000,
    reasoningEffort: "high",
  },
  { id: "codex", name: "Codex", model: "openai-codex/gpt-5.5", provider: "openai_codex" },
];
it("opens setup without replacing its prompt with a preset or showing a repeated tooltip", async () => {
  const action = vi.fn();
  const user = userEvent.setup();
  render(
    <ModelSelector label="Choose your AI" modelPresets={presets} needsSetup onClick={action} />,
  );
  const button = screen.getByRole("button", { name: "Choose your AI" });
  await user.hover(button);
  expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  await user.click(button);
  expect(action).toHaveBeenCalledOnce();
});
it("switches a preset by its ID and returns editing focus", async () => {
  const change = vi.fn();
  const focus = vi.fn();
  const user = userEvent.setup();
  render(
    <ModelSelector
      label="Zhipu"
      modelPreset="zhipu"
      modelPresets={presets}
      onPresetChange={change}
      onRequestComposerFocus={focus}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Zhipu" }));
  const menu = screen.getByRole("menu", { name: "Zhipu" });
  expect(within(menu).getByRole("menuitemradio", { name: /Zhipu/ })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await user.click(within(menu).getByRole("menuitemradio", { name: /Codex/ }));
  expect(change).toHaveBeenCalledWith("codex");
  await waitFor(() => expect(focus).toHaveBeenCalledOnce());
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
});
it("keeps model management available with one preset", async () => {
  const manage = vi.fn();
  const user = userEvent.setup();
  render(
    <ModelSelector
      label="Zhipu"
      modelPreset="zhipu"
      modelPresets={presets.slice(0, 1)}
      onManageModels={manage}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Zhipu" }));
  await user.click(screen.getByRole("menuitem", { name: "Manage presets" }));
  expect(manage).toHaveBeenCalledOnce();
});
it("offers management without inventing a default preset", async () => {
  render(<ModelSelector label="No model" onManageModels={vi.fn()} />);
  await userEvent.setup().click(screen.getByRole("button", { name: "No model" }));
  expect(screen.queryByRole("menuitemradio")).not.toBeInTheDocument();
  expect(screen.getByRole("menuitem", { name: "Manage presets" })).toBeVisible();
});
it.each([false, true])("shows model details with a working selection menu: %s", async selectable => {
  render(
    <ModelSelector
      label="Zhipu"
      modelPreset="zhipu"
      modelPresets={presets}
      modelDetail="glm-5"
      onPresetChange={selectable ? vi.fn() : undefined}
      providerLabel="Zhipu AI"
    />,
  );
  await userEvent.setup().hover(screen.getByRole("button", { name: "Zhipu" }));
  const hint = await screen.findByRole("tooltip");
  expect(hint).toHaveTextContent("glm-5");
  expect(hint).toHaveTextContent("Zhipu AI");
  expect(hint).toHaveTextContent("high");
});
it("supports keyboard open and Escape without changing the model", async () => {
  const change = vi.fn();
  const user = userEvent.setup();
  render(
    <ModelSelector
      label="Zhipu"
      modelPreset="zhipu"
      modelPresets={presets}
      onPresetChange={change}
    />,
  );
  screen.getByRole("button", { name: "Zhipu" }).focus();
  await user.keyboard("{Enter}");
  expect(screen.getByRole("menu")).toBeVisible();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(change).not.toHaveBeenCalled();
});
it("focuses an explicitly requested configuration action", () => {
  const { rerender } = render(
    <ModelSelector label="Configure model" needsSetup onClick={vi.fn()} />,
  );
  rerender(
    <ModelSelector label="Configure model" needsSetup attentionRequest={1} onClick={vi.fn()} />,
  );
  expect(screen.getByRole("button", { name: "Configure model" })).toHaveFocus();
});
it("does not call the model setter when selecting the current preset", async () => {
  const change = vi.fn();
  render(
    <ModelSelector
      label="Zhipu"
      modelPreset="zhipu"
      modelPresets={presets}
      onPresetChange={change}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Zhipu" }));
  await userEvent.setup().click(screen.getByRole("menuitemradio", { name: /Zhipu/ }));
  expect(change).not.toHaveBeenCalled();
});
