import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AccountSettings } from "@/features/settings/account/AccountSettings";
import * as account from "@/lib/account";
import { setAppLanguage } from "@/i18n";

beforeEach(async () => {
  await setAppLanguage("en");
  vi.spyOn(account, "accountStatus").mockResolvedValue({ enabled: true, authenticated: true, registration_required: false, username: "owner" });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

async function fill(newPassword = "NewPassword!", confirmPassword = newPassword) {
  await screen.findByText("owner");
  fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "OldPassword!" } });
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: newPassword } });
  fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: confirmPassword } });
  fireEvent.submit(screen.getByRole("button", { name: "Change password" }).closest("form")!);
}

it("changes the password and clears sensitive form values after success", async () => {
  const request = vi.spyOn(account, "accountRequest").mockResolvedValue(undefined);
  render(<AccountSettings />);
  await fill();
  await waitFor(() => expect(request).toHaveBeenCalledWith("change-password", { current_password: "OldPassword!", new_password: "NewPassword!" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Password changed");
  expect(screen.getByLabelText("Current password")).toHaveValue("");
  expect(screen.getByLabelText("New password")).toHaveValue("");
});

it("validates password strength and confirmation without sending invalid changes", async () => {
  const request = vi.spyOn(account, "accountRequest").mockResolvedValue(undefined);
  render(<AccountSettings />);
  await fill("short");
  expect(screen.getByRole("alert")).toHaveTextContent("at least 10 characters");
  await fill("NewPassword!", "DifferentPassword!");
  expect(screen.getByRole("alert")).toHaveTextContent("match");
  expect(request).not.toHaveBeenCalled();
});

it("shows the incorrect-current-password reason and allows another attempt", async () => {
  vi.spyOn(account, "accountRequest").mockRejectedValue(new account.AccountRequestError("incorrect_password"));
  render(<AccountSettings />);
  await fill();
  expect(await screen.findByRole("alert")).toHaveTextContent("current password is incorrect");
  expect(screen.getByRole("button", { name: "Change password" })).toBeEnabled();
  expect(screen.getByLabelText("New password")).toHaveAttribute("type", "password");
  fireEvent.click(screen.getByRole("button", { name: "Show password" }));
  expect(screen.getByLabelText("New password")).toHaveAttribute("type", "text");
});

it("explains when browser account authentication is disabled", async () => {
  vi.mocked(account.accountStatus).mockResolvedValue({ enabled: false, authenticated: false, registration_required: false, username: null });
  render(<AccountSettings />);
  expect(await screen.findByText(/available when using browser registration/)).toBeInTheDocument();
  expect(screen.queryByLabelText("Current password")).not.toBeInTheDocument();
});

it("can retry an account status request that failed", async () => {
  vi.mocked(account.accountStatus).mockRejectedValueOnce(new Error("offline"));
  render(<AccountSettings />);
  expect(await screen.findByRole("alert")).toHaveTextContent("connect");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("owner")).toBeInTheDocument();
});
