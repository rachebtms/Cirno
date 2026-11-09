import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RouterHeartbeatButton } from "@/components/thread/RouterHeartbeatButton";
import type { CirnoClient } from "@/lib/cirno-client";
import "@/i18n";

describe("Router heartbeat control", () => {
  it("shows persisted pause state and resumes only after the server accepts", async () => {
    let paused = true;
    const requestMutation = vi.fn(async (_: string, payload: { action: string; values: { paused?: boolean } }) => {
      if (payload.action.endsWith(".update")) paused = payload.values.paused!;
      return { paused, enabled: true };
    });
    const client = { requestMutation, onSessionUpdate: vi.fn(() => vi.fn()), onStatus: vi.fn(() => vi.fn()) } as unknown as CirnoClient;
    render(<RouterHeartbeatButton client={client} />);
    const resume = await screen.findByRole("button", { name: "Resume heartbeat" });
    expect(resume).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(resume);
    await waitFor(() => expect(screen.getByRole("button", { name: "Pause heartbeat" })).toHaveAttribute("aria-pressed", "false"));
    expect(requestMutation).toHaveBeenCalledWith("instance.action", { action: "router.heartbeat.update", values: { paused: false } });
  });

  it("keeps pause state and exposes a failed resume request", async () => {
    const requestMutation = vi.fn().mockResolvedValueOnce({ paused: true, enabled: true }).mockRejectedValueOnce(new Error("Disconnected"));
    const client = { requestMutation, onSessionUpdate: vi.fn(() => vi.fn()), onStatus: vi.fn(() => vi.fn()) } as unknown as CirnoClient;
    render(<RouterHeartbeatButton client={client} />);
    await userEvent.click(await screen.findByRole("button", { name: "Resume heartbeat" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Disconnected");
    expect(screen.getByRole("button", { name: "Resume heartbeat" })).toHaveAttribute("aria-pressed", "true");
  });
});
