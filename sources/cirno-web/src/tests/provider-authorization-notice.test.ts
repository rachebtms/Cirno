import { afterEach, expect, it, vi } from "vitest";
import { toast } from "@heroui/react";
import { cancelProviderOAuth } from "@/lib/api";
import type { CirnoClient } from "@/lib/cirno-client";
import { releaseAuthorization } from "@/features/settings/providers/oauth/releaseAuthorization";

vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  cancelProviderOAuth: vi.fn(),
}));
const client = {} as CirnoClient;
const flow = {
  status: "authorization_required",
  provider: "github_copilot",
  flow_id: "inactive-flow",
  authorization_url: "https://github.com/login/device",
  expires_in: 600,
} as const;
afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(cancelProviderOAuth).mockReset();
});

it("keeps failed release visible until the user retries successfully", async () => {
  const failure = new Error("Release unavailable");
  vi.mocked(cancelProviderOAuth).mockRejectedValueOnce(failure).mockResolvedValueOnce(undefined);
  const show = vi.spyOn(toast, "danger").mockReturnValue("notice");
  const update = vi.spyOn(toast, "update").mockReturnValue("notice"),
    close = vi.spyOn(toast, "close").mockImplementation(() => {});
  await releaseAuthorization(client, flow);
  expect(cancelProviderOAuth).toHaveBeenCalledTimes(1);
  expect(show).toHaveBeenCalledWith(
    expect.stringContaining(flow.provider),
    expect.objectContaining({ description: failure.message, timeout: 0 }),
  );
  await show.mock.calls[0][1]?.actionProps?.onPress?.({} as never);
  expect(update).toHaveBeenCalledWith(
    "notice",
    expect.any(String),
    expect.objectContaining({ isLoading: true }),
  );
  expect(cancelProviderOAuth).toHaveBeenCalledTimes(2);
  expect(close).toHaveBeenCalledWith("notice");
});

it("updates the same notice if its retry also fails", async () => {
  vi.mocked(cancelProviderOAuth).mockRejectedValue(new Error("Still unavailable"));
  const show = vi.spyOn(toast, "danger").mockReturnValue("notice");
  const update = vi.spyOn(toast, "update").mockReturnValue("notice");
  await releaseAuthorization(client, flow);
  await show.mock.calls[0][1]?.actionProps?.onPress?.({} as never);
  expect(show).toHaveBeenCalledTimes(1);
  expect(update).toHaveBeenLastCalledWith(
    "notice",
    expect.any(String),
    expect.objectContaining({ description: "Still unavailable", isLoading: false }),
  );
});
