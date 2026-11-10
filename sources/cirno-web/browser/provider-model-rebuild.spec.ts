import { expect, test } from "@playwright/test";
for (const width of [390, 1440]) for (const theme of ["light", "dark"]) {
  test(`provider settings preserve the model draft at ${width}px in ${theme}`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/browser/fixture.html?case=provider-model-rebuild&lang=en&theme=${theme}`);
    await page.getByRole("button", { name: "New preset", exact: true }).click();
    const draft = page.getByRole("dialog", { name: "New preset", exact: true });
    await draft.getByRole("textbox", { name: /^Preset name/ }).fill("Keep this draft");
    const model = draft.getByRole("combobox", { name: "Model", exact: true });
    await model.fill("analysis-model");
    await expect(page.getByRole("listbox")).toBeVisible();
    await page.getByRole("option", { name: "analysis-model", exact: true }).click();
    await expect(page.getByRole("listbox")).not.toBeVisible();
    await draft.getByRole("button", { name: "Configure", exact: true }).click();
    const provider = page.getByRole("dialog", { name: "OpenAI", exact: true });
    await provider.getByRole("textbox", { name: "API URL", exact: true }).fill("https://draft.example/v1");
    await provider.getByRole("button", { name: "Advanced options", exact: true }).click();
    const proxy = provider.getByRole("switch", { name: "Use proxy", exact: true });
    await provider.getByText("Use proxy", { exact: true }).click(); await expect(proxy).toBeChecked();
    const headers = provider.getByRole("textbox", { name: "Headers", exact: true });
    await headers.fill('{\n  "X-Experiment": "research"\n}');
    await expect(headers).toBeVisible();
    await page.screenshot({ path: test.info().outputPath("provider.png"), animations: "disabled" });
    await provider.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(draft.getByRole("textbox", { name: /^Preset name/ })).toHaveValue("Keep this draft");
    await expect(model).toHaveValue("analysis-model");
    await draft.getByRole("button", { name: "Advanced options", exact: true }).click();
    await expect(draft.getByRole("textbox", { name: /^Context window/ })).toBeVisible();
    await page.screenshot({ path: test.info().outputPath("model.png"), animations: "disabled" });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}

for (const width of [390, 1440]) test(`catalog failure remains actionable inside the model editor at ${width}px`, async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/browser/fixture.html?case=provider-model-rebuild&lang=en&theme=dark&catalogFailure");
  await page.getByRole("button", { name: "New preset", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "New preset", exact: true });
  const model = dialog.getByRole("combobox", { name: "Model", exact: true });
  await model.fill("analysis");
  const notice = page.getByRole("alert").filter({ hasText: "Refresh failed" });
  await expect(notice).toContainText("Cached list may be out of date.");
  await notice.getByRole("button", { name: "Error details", exact: true }).click();
  await expect(notice).toContainText("request research-42");
  await page.screenshot({ path: info.outputPath("catalog-error.png"), animations: "disabled" });
  await notice.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(notice).not.toBeVisible();
  await page.getByRole("option", { name: "analysis-model", exact: true }).click();
  await expect(model).toHaveValue("analysis-model");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

for (const width of [390, 1440]) test(`adding a provider restores the model draft and trigger focus at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/browser/fixture.html?case=provider-model-rebuild&lang=en&theme=light");
  await page.getByRole("button", { name: "New preset", exact: true }).click();
  const draft = page.getByRole("dialog", { name: "New preset", exact: true });
  await draft.getByRole("textbox", { name: /^Preset name/ }).fill("Keep my draft");
  const trigger = draft.getByRole("button", { name: "Add provider", exact: true });
  await trigger.click();
  await page.getByRole("option", { name: "DeepSeek", exact: true }).click();
  const provider = page.getByRole("dialog", { name: "DeepSeek", exact: true });
  await provider.getByPlaceholder("Enter API key", { exact: true }).fill("fixture-key");
  await provider.getByRole("button", { name: "Add provider", exact: true }).click();
  await expect(provider).toHaveCount(0);
  await expect(draft.getByRole("textbox", { name: /^Preset name/ })).toHaveValue("Keep my draft");
  await expect(draft.getByRole("button", { name: "DeepSeek Provider", exact: true })).toBeVisible();
  await expect(trigger).toBeFocused();
});

for (const width of [390, 1440]) test(`direct provider activation restores focus after save at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/browser/fixture.html?case=provider-model-rebuild&lang=en&theme=light");
  await page.getByRole("button", { name: "New preset", exact: true }).click();
  const draft = page.getByRole("dialog", { name: "New preset", exact: true });
  await draft.getByRole("textbox", { name: /^Preset name/ }).fill("Retained provider draft");
  const trigger = draft.getByRole("button", { name: "Configure", exact: true });
  await trigger.evaluate(button => (button as HTMLButtonElement).click());
  const provider = page.getByRole("dialog", { name: "OpenAI", exact: true });
  await provider.getByRole("textbox", { name: "API URL", exact: true }).fill("https://saved.example/v1");
  await provider.getByRole("button", { name: "Save provider", exact: true }).click();
  await expect(provider).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(draft.getByRole("textbox", { name: /^Preset name/ })).toHaveValue("Retained provider draft");
  await trigger.click();
  await expect(provider.getByRole("textbox", { name: "API URL", exact: true })).toHaveValue("https://saved.example/v1");
});

for (const width of [390, 1440]) test(`cancelling provider settings returns to the model draft at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/browser/fixture.html?case=provider-model-rebuild&lang=en&theme=light");
  await page.getByRole("button", { name: "New preset", exact: true }).click();
  const draft = page.getByRole("dialog", { name: "New preset", exact: true });
  await draft.getByRole("textbox", { name: /^Preset name/ }).fill("Keep my draft");
  const trigger = draft.getByRole("button", { name: "Configure", exact: true });
  await trigger.click();
  const provider = page.getByRole("dialog", { name: "OpenAI", exact: true });
  await provider.getByRole("textbox", { name: "API URL", exact: true }).fill("https://unsaved.example/v1");
  await provider.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(provider).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(draft.getByRole("textbox", { name: /^Preset name/ })).toHaveValue("Keep my draft");
  await trigger.click();
  await expect(provider.getByRole("textbox", { name: "API URL", exact: true })).not.toHaveValue("https://unsaved.example/v1");
});
