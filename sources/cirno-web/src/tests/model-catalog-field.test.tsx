import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ReasoningEffortPicker } from "@/features/settings/models/ReasoningEffortPicker";
import { ModelCatalogField } from "@/features/settings/models/ui/ModelCatalogField";
import { useState } from "react";
afterEach(() => vi.unstubAllGlobals());
it("opens the full catalog for an existing selection and filters only when the user types", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      Response.json({
        provider: "choices",
        status: "available",
        catalog_kind: "official",
        models: [{ id: "first" }, { id: "second" }],
        model_count: 2,
      }),
    ),
  );
  const provider = {
    id: "choices",
    name: "Choices",
    configured: true,
    model_catalog: "official" as const,
  };
  function Field() {
    const [value, setValue] = useState("first");
    return (
      <ModelCatalogField
        token="choices-test"
        provider={provider}
        value={value}
        onChange={setValue}
      />
    );
  }
  render(<Field />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Show suggestions Model" }));
  expect(await screen.findByRole("option", { name: "second" })).toBeVisible();
  const input = screen.getByRole("combobox", { name: "Model" });
  await user.clear(input);
  await user.type(input, "sec");
  expect(screen.queryByRole("option", { name: "first" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("option", { name: "second" }));
  expect(input).toHaveValue("second");
});
it("loads an empty asynchronous catalog and offers sign-in when authorization expires", async () => {
  const fetch = vi.fn(async () =>
    Response.json({
      provider: "github_copilot",
      status: "available",
      catalog_kind: "hybrid",
      source: "fallback",
      error_kind: "auth_required",
      models: [{ id: "model" }],
      model_count: 1,
    }),
  );
  vi.stubGlobal("fetch", fetch);
  const signIn = vi.fn();
  const provider = {
    id: "github_copilot",
    name: "Copilot",
    configured: true,
    auth_type: "oauth" as const,
    model_catalog: "hybrid" as const,
  };
  function Field() {
    const [value, setValue] = useState("");
    return (
      <ModelCatalogField
        token="catalog-test"
        provider={provider}
        value={value}
        onChange={setValue}
        onSignIn={signIn}
      />
    );
  }
  render(<Field />);
  await userEvent.setup().click(screen.getByRole("button", { name: "Show suggestions Model" }));
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  await userEvent.setup().click(await screen.findByRole("button", { name: "Sign in again" }));
  expect(signIn).toHaveBeenCalledWith("github_copilot");
});
it("keeps the default effort as an empty API value rather than the translated label", async () => {
  const fetch = vi.fn(async () =>
    Response.json({
      provider: "test",
      status: "available",
      catalog_kind: "official",
      models: [{ id: "model", reasoning_efforts: ["low", "high"] }],
      model_count: 1,
    }),
  );
  vi.stubGlobal("fetch", fetch);
  const provider = {
    id: "test",
    name: "Test",
    configured: true,
    model_catalog: "official" as const,
  };
  let current = "high";
  function Field() {
    const [value, setValue] = useState("high");
    current = value;
    return (
      <ReasoningEffortPicker
        token="reasoning-test"
        provider={provider}
        model="model"
        value={value}
        onChange={setValue}
      />
    );
  }
  render(<Field />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Show suggestions Reasoning effort" }));
  await user.click(await screen.findByRole("option", { name: "Default" }));
  expect(current).toBe("");
});

it("retains saved reasoning choices while exposing catalog failure and retry", async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new Error("Reasoning catalog unavailable"))
    .mockResolvedValueOnce(Response.json({ provider: "retry-effort", status: "available", catalog_kind: "official",
      models: [{ id: "model", reasoning_efforts: ["high", "max"] }], model_count: 1 }));
  vi.stubGlobal("fetch", fetch);
  const provider = { id: "retry-effort", name: "Retry effort", configured: true, model_catalog: "official" as const };
  render(<ReasoningEffortPicker token="retry-effort" provider={provider} model="model" savedValues={["high"]} value="" onChange={() => {}} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Show suggestions Reasoning effort" }));
  expect(await screen.findByRole("alert")).toBeVisible();
  expect(screen.getByRole("option", { name: "high" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Error details" }));
  expect(screen.getByText("Reasoning catalog unavailable")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("option", { name: "max" })).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(2);
});
