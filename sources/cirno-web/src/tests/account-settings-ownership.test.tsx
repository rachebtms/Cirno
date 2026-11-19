import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useAccountSettings } from "@/features/settings/account/useAccountSettings";
import * as api from "@/lib/account";
import { setAppLanguage } from "@/i18n";

const initial: api.AccountStatus = {
  enabled: true, authenticated: true, registration_required: false, username: "owner", router_handle: "cirno",
};
function pending<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
beforeEach(async () => {
  await setAppLanguage("en");
  vi.spyOn(api, "accountStatus").mockResolvedValue(initial);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("admits only one password mutation when submit repeats before React renders busy", async () => {
  const accepted = pending<void>();
  const request = vi.spyOn(api, "accountRequest").mockImplementation(() => accepted.promise);
  const view = renderHook(useAccountSettings);
  await waitFor(() => expect(view.result.current.account).toEqual(initial));
  act(() => {
    view.result.current.change("current", "OldPassword!");
    view.result.current.change("next", "NewPassword!");
    view.result.current.change("confirm", "NewPassword!");
  });
  try {
    act(() => {
      void view.result.current.submit();
      void view.result.current.submit();
    });
    expect(request).toHaveBeenCalledTimes(1);
  } finally {
    await act(async () => { accepted.resolve(); });
  }
  expect(view.result.current.saved).toBe(true);
  expect(view.result.current.passwords).toEqual({ current: "", next: "", confirm: "" });
});

it("does not overwrite a confirmed Router rename with an older locale-triggered status read", async () => {
  const delayed = pending<api.AccountStatus>();
  const view = renderHook(useAccountSettings);
  await waitFor(() => expect(view.result.current.account).toEqual(initial));
  vi.mocked(api.accountStatus).mockImplementationOnce(() => delayed.promise);
  await act(async () => { await setAppLanguage("zh-CN"); });
  await waitFor(() => expect(api.accountStatus).toHaveBeenCalledTimes(2));
  act(() => { view.result.current.setAccount({ ...initial, router_handle: "snow" }); });
  await act(async () => { delayed.resolve(initial); });
  expect(view.result.current.account?.router_handle).toBe("snow");
});
