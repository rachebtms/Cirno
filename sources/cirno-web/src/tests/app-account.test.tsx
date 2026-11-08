import {
  installAppTestLifecycle,
  connectSpy,
  updateUrlSpy,
} from "./helpers/app-harness";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { readOwnerPreferences } from "@/features/preferences/store";
import {
  BootstrapAuthRequiredError,
  deriveWsUrl,
  fetchBootstrap,
} from "@/lib/bootstrap";
import App from "@/App";

describe("App account", () => {
  installAppTestLifecycle();

  it("shows the auth form without an invalid-password error on first load", async () => {
    vi.mocked(fetchBootstrap).mockRejectedValueOnce(
      new Error("bootstrap failed: HTTP 401"),
    );

    render(<App />);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Connect to Cirno",
      }),
    ).toBeInTheDocument();
    const password = screen.getByLabelText("WebUI password");
    expect(password).not.toHaveAttribute("aria-describedby");
    expect(password).toHaveAttribute("autocomplete", "current-password");
    expect(password).not.toHaveAttribute("placeholder");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(connectSpy).not.toHaveBeenCalled();
  });

  it("switches language before connecting while preserving the password draft", async () => {
    vi.mocked(fetchBootstrap).mockRejectedValueOnce(
      new Error("bootstrap failed: HTTP 401"),
    );
    const user = userEvent.setup();

    render(<App />);

    await user.type(
      await screen.findByLabelText("WebUI password"),
      "draft-password",
    );
    await user.tab({ shift: true });
    expect(
      screen.getByRole("button", { name: /Change language/ }),
    ).toHaveFocus();
    await user.keyboard("{Enter}");
    await screen.findByRole("listbox");
    await user.click(screen.getByRole("option", { name: "简体中文" }));

    expect(
      await screen.findByRole("heading", { name: "连接到 Cirno" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("WebUI 密码")).toHaveValue("draft-password");
    expect(screen.getByRole("button", { name: "连接" })).toBeEnabled();
    expect(document.documentElement.lang).toBe("zh-CN");
    expect(readOwnerPreferences().language).toBe("zh-CN");
    expect(fetchBootstrap).toHaveBeenCalledTimes(1);
    expect(connectSpy).not.toHaveBeenCalled();
  });

  it("reveals password setup help with the keyboard without submitting the form", async () => {
    vi.mocked(fetchBootstrap).mockRejectedValueOnce(
      new Error("bootstrap failed: HTTP 401"),
    );
    const user = userEvent.setup();

    render(<App />);

    const password = await screen.findByLabelText("WebUI password");
    await user.type(password, "draft-password");
    await user.tab();
    await user.tab();
    await user.tab();
    const help = screen.getByRole("button", {
      name: "Where can I find the password?",
    });
    expect(help).toHaveFocus();
    expect(help).toHaveAttribute("aria-expanded", "false");
    const content = document.getElementById(
      help.getAttribute("aria-controls")!,
    );
    expect(content).toHaveAttribute("aria-hidden", "true");

    await user.keyboard("{Enter}");

    expect(help).toHaveAttribute("aria-expanded", "true");
    await waitFor(() => expect(content).toHaveAttribute("aria-hidden", "false"));
    expect(content).toHaveTextContent("~/.cirno/config.json");
    expect(content).toHaveTextContent("channels.websocket.tokenIssueSecret");
    expect(content).toHaveTextContent(
      "If that value is empty, use channels.websocket.token.",
    );

    await user.keyboard(" ");

    expect(help).toHaveAttribute("aria-expanded", "false");
    expect(password).toHaveValue("draft-password");
    expect(fetchBootstrap).toHaveBeenCalledTimes(1);
  });

  it("toggles password visibility without changing the password", async () => {
    vi.mocked(fetchBootstrap).mockRejectedValueOnce(
      new Error("bootstrap failed: HTTP 401"),
    );
    const user = userEvent.setup();

    render(<App />);

    const password = await screen.findByLabelText("WebUI password");
    await user.type(password, "correct horse battery staple");
    expect(password).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: "Show password" }));

    expect(password).toHaveAttribute("type", "text");
    expect(password).toHaveValue("correct horse battery staple");
    const hidePassword = screen.getByRole("button", { name: "Hide password" });
    expect(hidePassword).toHaveFocus();

    await user.click(hidePassword);

    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveValue("correct horse battery staple");
    expect(screen.getByRole("button", { name: "Show password" })).toHaveFocus();
  });

  it("explains and focuses an empty auth password", async () => {
    vi.mocked(fetchBootstrap).mockRejectedValue(
      new Error("bootstrap failed: HTTP 401"),
    );

    render(<App />);

    const password = await screen.findByLabelText("WebUI password");
    const connect = screen.getByRole("button", { name: "Connect" });
    expect(connect).toBeEnabled();
    fireEvent.click(connect);

    expect(await screen.findByText("Enter password")).toBeVisible();
    expect(password).not.toHaveAttribute("placeholder");
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(document.getElementById(password.getAttribute("aria-describedby")!)).toHaveTextContent("Enter password");
    expect(password).toHaveFocus();
    fireEvent.change(password, { target: { value: "   " } });
    fireEvent.click(connect);
    expect(password).toHaveValue("");
    expect(password).not.toHaveAttribute("placeholder");
    expect(fetchBootstrap).toHaveBeenCalledTimes(1);
  });

  it("shows the auth form when bootstrap does not issue an API token", async () => {
    vi.mocked(fetchBootstrap).mockRejectedValueOnce(
      new BootstrapAuthRequiredError(
        "bootstrap authentication required: missing api_token",
      ),
    );

    render(<App />);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Connect to Cirno",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(connectSpy).not.toHaveBeenCalled();
  });

  it("shows an invalid-password error after a submitted password is rejected", async () => {
    vi.mocked(fetchBootstrap).mockRejectedValue(
      new Error("bootstrap failed: HTTP 401"),
    );

    render(<App />);

    const password = await screen.findByLabelText("WebUI password");
    fireEvent.change(password, { target: { value: "wrong-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    const retryPassword = await screen.findByLabelText("WebUI password");
    expect(await screen.findByText("Incorrect password")).toBeVisible();
    expect(retryPassword).not.toHaveAttribute("placeholder");
    expect(retryPassword).toHaveValue("");
    expect(retryPassword).toHaveAttribute("aria-invalid", "true");
    expect(retryPassword).toHaveFocus();
    expect(fetchBootstrap).toHaveBeenLastCalledWith("", "wrong-password");
    expect(connectSpy).not.toHaveBeenCalled();
    fireEvent.change(retryPassword, { target: { value: "retry-password" } });
    expect(retryPassword).not.toHaveAttribute("placeholder");
    expect(retryPassword).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps rejected-password feedback visible until the user edits it", async () => {
    vi.mocked(fetchBootstrap).mockRejectedValue(new Error("bootstrap failed: HTTP 401"));
    render(<App />);
    const password = await screen.findByLabelText("WebUI password");
    fireEvent.change(password, { target: { value: "wrong-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText("Incorrect password")).toBeVisible();
    vi.useFakeTimers();
    act(() => vi.advanceTimersByTime(30_000));
    expect(screen.getByText("Incorrect password")).toBeVisible();
    const retryPassword = screen.getByLabelText("WebUI password");
    expect(retryPassword).toHaveFocus();
    fireEvent.change(retryPassword, { target: { value: "retry-password" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(retryPassword).toHaveValue("retry-password");
  });

  it("refreshes the bootstrap token before REST settings auth expires", async () => {
    vi.useFakeTimers();
    vi.mocked(fetchBootstrap)
      .mockResolvedValueOnce({
        token: "tok-1",
        api_token: "api-tok-1",
        ws_path: "/",
        expires_in: 30,
      })
      .mockResolvedValueOnce({
        token: "tok-2",
        api_token: "api-tok-2",
        ws_path: "/",
        expires_in: 300,
      });
    vi.mocked(deriveWsUrl).mockImplementation(
      (_wsPath, token) => `ws://test?token=${token}`,
    );

    const { unmount } = render(<App />);
    await act(async () => {});

    expect(connectSpy).toHaveBeenCalled();
    expect(fetchBootstrap).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });

    expect(fetchBootstrap).toHaveBeenCalledTimes(2);
    expect(updateUrlSpy).toHaveBeenCalledWith("ws://test?token=tok-2");
    unmount();
  });
});
