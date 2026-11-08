import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError, cancelProviderOAuth, completeProviderOAuth } from "@/lib/api";
import type { CirnoClient } from "@/lib/cirno-client";
import { AuthorizationFlow } from "@/features/settings/providers/oauth/AuthorizationFlow";
import { settingsPayload } from "./settings-test-utils";

vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  cancelProviderOAuth: vi.fn(),
  completeProviderOAuth: vi.fn(),
}));
const cancel = vi.mocked(cancelProviderOAuth),
  complete = vi.mocked(completeProviderOAuth);
const client = {} as CirnoClient;
const flow = {
  status: "authorization_required",
  provider: "github_copilot",
  flow_id: "flow",
  authorization_url: "https://github.com/login/device",
  expires_in: 600,
  completion_input: "device_code",
} as const;
const pending = { status: "pending", provider: flow.provider, flow_id: flow.flow_id } as const;
function setup() {
  const connected = vi.fn(),
    closed = vi.fn();
  return { session: new AuthorizationFlow(client, flow, connected, closed), connected, closed };
}
beforeEach(() => {
  vi.useFakeTimers();
  complete.mockReset();
  cancel.mockReset().mockResolvedValue(undefined);
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

it("polls pending authorization and stops after the completed settings arrive", async () => {
  complete.mockResolvedValueOnce(pending).mockResolvedValueOnce(settingsPayload());
  const { session, connected } = setup();
  session.start();
  await vi.advanceTimersByTimeAsync(1000);
  expect(connected).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1000);
  expect(connected).toHaveBeenCalledExactlyOnceWith(settingsPayload());
  await session.dispose();
  await vi.advanceTimersByTimeAsync(5000);
  expect(complete).toHaveBeenCalledTimes(2);
  expect(cancel).not.toHaveBeenCalled();
});

it("serializes manual completion behind an active poll without losing the response", async () => {
  let finish!: (value: typeof pending) => void;
  complete
    .mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    )
    .mockResolvedValueOnce(settingsPayload());
  const { session, connected } = setup();
  const poll = session.poll();
  await Promise.resolve();
  const manual = session.submit("callback");
  expect(complete).toHaveBeenCalledTimes(1);
  expect(session.getSnapshot().phase).toBe("completing");
  finish(pending);
  await poll;
  await manual;
  expect(complete).toHaveBeenLastCalledWith(client, flow.provider, flow.flow_id, "callback");
  expect(connected).toHaveBeenCalledTimes(1);
});

it("retains poll failures for explicit retry instead of polling indefinitely", async () => {
  complete
    .mockRejectedValueOnce(new Error("Provider unavailable"))
    .mockResolvedValueOnce(settingsPayload());
  const { session, connected } = setup();
  await session.poll();
  expect(session.getSnapshot()).toEqual({ phase: "failed", error: "Provider unavailable" });
  await vi.advanceTimersByTimeAsync(5000);
  expect(complete).toHaveBeenCalledTimes(1);
  await session.poll();
  expect(connected).toHaveBeenCalledTimes(1);
});

it("keeps cancellation failures visible and closes only after a successful retry", async () => {
  cancel.mockRejectedValueOnce(new Error("Cancel unavailable"));
  const { session, closed } = setup();
  session.start();
  await session.close();
  expect(session.getSnapshot()).toEqual({ phase: "cancel_failed", error: "Cancel unavailable" });
  await vi.advanceTimersByTimeAsync(5000);
  expect(complete).not.toHaveBeenCalled();
  expect(closed).not.toHaveBeenCalled();
  await session.close();
  expect(closed).toHaveBeenCalledTimes(1);
});

it("accepts an expired flow as already released", async () => {
  cancel.mockRejectedValueOnce(new ApiError(410, "Expired"));
  const { session, closed } = setup();
  await session.close();
  expect(session.getSnapshot().phase).toBe("closed");
  expect(closed).toHaveBeenCalledTimes(1);
});

it("does not apply completion that arrives after closing the flow", async () => {
  let finish!: (value: ReturnType<typeof settingsPayload>) => void;
  complete.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const { session, connected, closed } = setup();
  const poll = session.poll();
  await Promise.resolve();
  await session.close();
  finish(settingsPayload());
  await poll;
  expect(connected).not.toHaveBeenCalled();
  expect(closed).toHaveBeenCalledTimes(1);
});

it("propagates disposal failures to the surviving notification owner", async () => {
  cancel.mockRejectedValueOnce(new Error("Release failed"));
  const { session } = setup();
  await expect(session.dispose()).rejects.toThrow("Release failed");
});
