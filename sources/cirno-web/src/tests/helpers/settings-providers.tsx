import { fireEvent, screen } from "@testing-library/react";
import { renderSettingsView } from "@/tests/settings-test-utils";

export function renderProviderManager(options: Parameters<typeof renderSettingsView>[0]) {
  const result = renderSettingsView(options);
  fireEvent.click(screen.getByRole("button", { name: "Manage providers" }));
  return result;
}

export function providerDialog() {
  return screen.getByRole("dialog", { name: /^(?!New preset$)/ });
}

export async function chooseProviderToConfigure(label: string) {
  fireEvent.click(await screen.findByRole("button", { name: "Add provider" }));
  fireEvent.click(await screen.findByRole("option", { name: label }));
}
