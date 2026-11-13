import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { CredentialsTab } from "@/features/credentials/CredentialsTab";
import type { CirnoClient } from "@/lib/cirno-client";
import { installSettingsViewTestHooks } from "./settings-test-utils";
installSettingsViewTestHooks();

it.each(["token", "password", "ssh"])("reveals and remasks a saved %s without changing or saving it", async kind => {
  const record = { id: "record", label: "Example credential", kind };
  const ssh = { host: "server", username: "owner", port: 22, auth_method: "password", has_password: true,
    identity_file: "", host_key: "", node_enabled: false, working_directory: "", init_script: "", environment: {} };
  const request = vi.fn(async (_name, payload) => {
    if (payload.action === "credentials.list") return { records: [record] };
    if (payload.action === "credentials.describe") return { ssh };
    if (payload.action === "credentials.reveal") return kind === "ssh" ? { ssh: { ...ssh, password: "fixture-private-value" } } : { value: "fixture-private-value", username: "owner" };
    throw new Error("Unexpected mutation");
  });
  const client = { requestMutation: request } as unknown as CirnoClient;
  const view = render(<CredentialsTab client={client} active />);
  fireEvent.click(await screen.findByRole("button", { name: /Example credential/ }));
  const reveal = await screen.findByRole("button", { name: "Reveal saved value" });
  await waitFor(() => expect(reveal).toBeEnabled());
  fireEvent.click(reveal);
  const value = await screen.findByDisplayValue("fixture-private-value");
  expect(value).toHaveAttribute("type", "text");
  fireEvent.click(screen.getByRole("button", { name: "Hide secret" }));
  expect(value).toHaveAttribute("type", "password");
  fireEvent.click(screen.getByRole("button", { name: "Show secret" }));
  expect(value).toHaveAttribute("type", "text");
  expect(request.mock.calls.filter(([, payload]) => payload.action === "credentials.reveal")).toHaveLength(1);
  expect(request.mock.calls.some(([, payload]) => payload.action === "credentials.save")).toBe(false);
  view.rerender(<CredentialsTab client={client} active={false} />);
  expect(screen.queryByDisplayValue("fixture-private-value")).not.toBeInTheDocument();
});
