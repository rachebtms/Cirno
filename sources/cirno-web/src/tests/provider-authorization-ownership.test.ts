import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { loginProviderOAuth, completeProviderOAuth, cancelProviderOAuth } from "@/lib/api";
import type { CirnoClient } from "@/lib/cirno-client";
import type {
  ProviderOAuthAuthorizationRequired,
  ProviderOAuthLoginResult,
} from "@/lib/contracts/models";
import { useProviderAuthorization } from "@/features/settings/providers/oauth/useProviderAuthorization";
import {
  releaseAuthorization,
  reportAuthorizationReleaseError,
} from "@/features/settings/providers/oauth/releaseAuthorization";
import { settingsPayload } from "./settings-test-utils";

vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  loginProviderOAuth: vi.fn(),
  completeProviderOAuth: vi.fn(),
  cancelProviderOAuth: vi.fn(),
}));
vi.mock("@/features/settings/providers/oauth/releaseAuthorization", () => ({
  releaseAuthorization: vi.fn(),
  reportAuthorizationReleaseError: vi.fn(),
}));
const client = {} as CirnoClient;
const flow: ProviderOAuthAuthorizationRequired = {
  status: "authorization_required",
  provider: "github_copilot",
  flow_id: "owned-flow",
  authorization_url: "https://github.com/login/device",
  expires_in: 600,
  completion_input: "device_code",
};
function setup() {
  const applyPayload = vi.fn(),
    setError = vi.fn();
  const view = renderHook(
    (owner) =>
      useProviderAuthorization({
        client: owner,
        busy: false,
        remoteBrowserAccess: true,
        applyPayload,
        setError,
      }),
    { initialProps: client },
  );
  return { ...view, applyPayload, setError };
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(loginProviderOAuth).mockReset();
  vi.mocked(completeProviderOAuth).mockReset();
  vi.mocked(cancelProviderOAuth).mockReset().mockResolvedValue(undefined);
  vi.mocked(releaseAuthorization).mockReset().mockResolvedValue(undefined);
  vi.mocked(reportAuthorizationReleaseError).mockReset();
});
afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.useRealTimers();
});

it.each(["device_code", "callback_url", "authorization_code"] as const)(
  "releases a late %s login instead of reopening a disposed editor",
  async (completion_input) => {
    let finish!: (value: ProviderOAuthLoginResult) => void;
    vi.mocked(loginProviderOAuth).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const { result, unmount, applyPayload } = setup();
    let pending!: unknown;
    act(() => {
      pending = result.current.login(flow.provider);
    });
    unmount();
    const late = { ...flow, completion_input };
    await act(async () => {
      finish(late);
      await pending;
    });
    expect(releaseAuthorization).toHaveBeenCalledExactlyOnceWith(client, late);
    expect(applyPayload).not.toHaveBeenCalled();
  },
);

it("ignores a settings acknowledgement after its owner has gone away", async () => {
  let finish!: (value: ProviderOAuthLoginResult) => void;
  vi.mocked(loginProviderOAuth).mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const { result, unmount, applyPayload, setError } = setup();
  let pending!: unknown;
  act(() => {
    pending = result.current.login("openai_codex");
  });
  unmount();
  await act(async () => {
    finish(settingsPayload());
    await pending;
  });
  expect(applyPayload).not.toHaveBeenCalled();
  expect(setError).not.toHaveBeenCalled();
});

it("cancels the old connection's flow and discards its late manual completion", async () => {
  vi.mocked(loginProviderOAuth).mockResolvedValueOnce(flow);
  let finish!: (value: ReturnType<typeof settingsPayload>) => void;
  vi.mocked(completeProviderOAuth).mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const { result, rerender, applyPayload } = setup();
  await act(() => result.current.login(flow.provider));
  act(() => result.current.setResponse("old callback"));
  let pending!: unknown;
  act(() => {
    pending = result.current.complete();
  });
  await act(async () => {});
  rerender({} as CirnoClient);
  await act(async () => {
    finish(settingsPayload());
    await pending;
  });
  expect(cancelProviderOAuth).toHaveBeenCalledExactlyOnceWith(client, flow.provider, flow.flow_id);
  expect(result.current.flow).toBeNull();
  expect(result.current.response).toBe("");
  expect(result.current.operation).toBeNull();
  expect(applyPayload).not.toHaveBeenCalled();
});

it("reports a failed cleanup to a notification that survives editor disposal", async () => {
  vi.mocked(loginProviderOAuth).mockResolvedValueOnce(flow);
  const error = new Error("Cleanup unavailable");
  vi.mocked(cancelProviderOAuth).mockRejectedValueOnce(error);
  const { result, unmount } = setup();
  await act(() => result.current.login(flow.provider));
  unmount();
  await act(async () => {});
  expect(reportAuthorizationReleaseError).toHaveBeenCalledExactlyOnceWith(client, flow, error);
});
