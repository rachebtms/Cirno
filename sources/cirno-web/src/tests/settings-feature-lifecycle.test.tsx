import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { SettingsFeature } from "@/features/settings/shared/SettingsFeature";

it("waits for a settings commit once and keeps its dialog open when the commit is rejected", async () => {
  let finish!: (saved: boolean) => void;
  const commit = vi.fn().mockImplementationOnce(() => new Promise<boolean>(resolve => { finish = resolve; })).mockResolvedValueOnce(true);
  render(<SettingsFeature title="Feature" enabled initialOpen onChange={vi.fn()} onBeforeClose={commit}><p>Draft configuration</p></SettingsFeature>);
  const dialog = screen.getByRole("dialog", { name: "Feature" });
  const close = screen.getByRole("button", { name: "Close" });
  fireEvent.click(close);
  fireEvent.click(close);
  expect(commit).toHaveBeenCalledTimes(1);
  expect(close).toBeDisabled();
  fireEvent.keyDown(dialog, { key: "Escape" });
  await act(async () => finish(false));
  expect(dialog).toBeInTheDocument();
  expect(close).toBeEnabled();
  fireEvent.click(close);
  await waitFor(() => expect(dialog).not.toBeInTheDocument());
  expect(commit).toHaveBeenCalledTimes(2);
});

it("exposes an unexpected close failure and allows another close attempt", async () => {
  const commit = vi.fn().mockRejectedValueOnce(new Error("Settings could not be saved")).mockResolvedValueOnce(true);
  render(<SettingsFeature title="Feature" enabled initialOpen onChange={vi.fn()} onBeforeClose={commit}><p>Draft configuration</p></SettingsFeature>);
  const dialog = screen.getByRole("dialog", { name: "Feature" });
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Settings could not be saved");
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  await waitFor(() => expect(dialog).not.toBeInTheDocument());
});
