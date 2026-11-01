import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountForm } from "@/components/setup/AccountForm";
import { BootstrapAuthRequiredError, fetchBootstrap } from "@/lib/bootstrap";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("browser account setup", () => {
  it("selects registration or account login from the gateway response", async () => {
    for (const [status, error, mode] of [[428, "registration_required", "register"], [401, "login_required", "login"]] as const) {
      vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error }), { status })));
      try {
        await fetchBootstrap();
        throw new Error("Expected authentication to be required");
      } catch (reason) {
        expect(reason).toBeInstanceOf(BootstrapAuthRequiredError);
        expect((reason as BootstrapAuthRequiredError).accountMode).toBe(mode);
      }
    }
    vi.stubGlobal("fetch", vi.fn(async () => new Response("Unauthorized", { status: 401 })));
    await expect(fetchBootstrap()).rejects.toMatchObject({ accountMode: undefined });
  });

  it("registers through a POST without storing a password in the browser", async () => {
    const request = vi.fn(async () => new Response('{"ok":true}', { status: 201 }));
    vi.stubGlobal("fetch", request);
    const onSuccess = vi.fn();
    const user = userEvent.setup();
    render(<AccountForm mode="register" onSuccess={onSuccess} />);
    await user.type(screen.getByLabelText("Username"), "owner");
    await user.type(screen.getByLabelText("Password", { exact: true }), "CirnoTest!");
    await user.type(screen.getByLabelText("Confirm password"), "CirnoTest!");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    expect(request).toHaveBeenCalledWith("/api/auth/register", expect.objectContaining({
      method: "POST", credentials: "same-origin", body: JSON.stringify({ username: "owner", password: "CirnoTest!" }),
    }));
    expect(Object.values(localStorage)).not.toContain("CirnoTest!");
  });

  it.each(["Short!A", "lowercase!", "UPPERCASEONLY", "Uppercase ", "Password中文", "PasswordA\u200b"])("rejects an incomplete password rule before registration: %s", async (password) => {
    const request = vi.fn();
    vi.stubGlobal("fetch", request);
    render(<AccountForm mode="register" onSuccess={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "owner" } });
    fireEvent.change(screen.getByLabelText("Password", { exact: true }), { target: { value: password } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: password } });
    fireEvent.submit(screen.getByRole("button", { name: "Create account" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Use at least 10 characters, including an uppercase letter and a symbol.");
    expect(request).not.toHaveBeenCalled();
  });

  it("does not truncate long passwords", async () => {
    const request = vi.fn(async () => new Response('{"ok":true}', { status: 201 }));
    vi.stubGlobal("fetch", request);
    render(<AccountForm mode="register" onSuccess={vi.fn()} />);
    const password = "A".repeat(1100) + "!";
    const field = screen.getByLabelText("Password", { exact: true });
    expect(field).not.toHaveAttribute("maxlength");
    expect(screen.getByLabelText("Confirm password")).not.toHaveAttribute("maxlength");
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "owner" } });
    fireEvent.change(field, { target: { value: password } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: password } });
    fireEvent.submit(screen.getByRole("button", { name: "Create account" }).closest("form")!);
    await waitFor(() => expect(request).toHaveBeenCalledWith("/api/auth/register", expect.objectContaining({ body: JSON.stringify({ username: "owner", password }) })));
  });

  it("keeps password confirmation errors beside the form", async () => {
    const request = vi.fn();
    vi.stubGlobal("fetch", request);
    render(<AccountForm mode="register" onSuccess={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "owner" } });
    fireEvent.change(screen.getByLabelText("Password", { exact: true }), { target: { value: "A long test password!" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "a different password" } });
    fireEvent.submit(screen.getByRole("button", { name: "Create account" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords do not match.");
    expect(request).not.toHaveBeenCalled();
  });

  it("shows login errors and leaves registration fields out of the login form", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response('{"error":"invalid_credentials"}', { status: 401 })));
    const user = userEvent.setup();
    render(<AccountForm mode="login" onSuccess={vi.fn()} />);
    expect(screen.queryByLabelText("Confirm password")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Username"), "owner");
    await user.type(screen.getByLabelText("Password", { exact: true }), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect username or password.");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });
});
