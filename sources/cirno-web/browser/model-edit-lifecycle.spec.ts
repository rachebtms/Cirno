import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  test(`repeated reasoning selection releases the picker focus at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/browser/fixture.html?case=provider-model-rebuild&lang=en&theme=dark&catalogFailure");
    await page.getByTestId("model-call-order-row-research").locator('button[aria-haspopup="dialog"]').click();
    const dialog = page.getByRole("dialog", { name: "Research", exact: true });
    const effort = dialog.getByRole("combobox", { name: "Reasoning effort", exact: true });
    for (let selection = 0; selection < 2; selection++) {
      await dialog.getByRole("button", { name: "Show suggestions Reasoning effort", exact: true }).click();
      if (selection === 0) {
        const error = page.getByRole("alert");
        await expect(error).toBeVisible();
        await error.getByRole("button", { name: "Error details", exact: true }).click();
        await expect(error).toContainText("Provider temporarily unavailable (request research-42)");
        await page.screenshot({ path: info.outputPath("reasoning-catalog-error.png"), animations: "disabled" });
        await error.getByRole("button", { name: "Retry", exact: true }).click();
        await expect(error).toHaveCount(0);
      }
      await page.getByRole("option", { name: "Default", exact: true }).click();
      await expect(page.getByRole("listbox")).toHaveCount(0);
      await expect(effort).toBeFocused();
    }
    const advanced = dialog.getByRole("button", { name: "Advanced options", exact: true });
    await advanced.click();
    await expect(advanced).toBeFocused();
    await expect(page.getByLabel("Model saves", { exact: true })).toHaveText("0");
    await dialog.getByRole("button", { name: "Show suggestions Reasoning effort", exact: true }).click();
    await page.getByRole("option", { name: "high", exact: true }).click();
    await expect(page.getByLabel("Model saves", { exact: true })).toHaveText("1");
    for (let selection = 0; selection < 2; selection++) {
      await dialog.getByRole("button", { name: "Show suggestions Reasoning effort", exact: true }).click();
      await page.getByRole("option", { name: "Default", exact: true }).click();
      await expect(page.getByRole("listbox")).toHaveCount(0);
    }
    await expect(page.getByLabel("Model saves", { exact: true })).toHaveText("2");
    expect(JSON.parse(await page.getByLabel("Model updates", { exact: true }).textContent() ?? "[]")).toEqual([
      { id: "research", reasoning_effort: "high" }, { id: "research", reasoning_effort: "" },
    ]);
    await expect(dialog.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  });

  test(`model drafts survive failed saves and API preview retries at ${width}px`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/browser/fixture.html?case=provider-model-rebuild&lang=en&theme=dark&modelSaveFailure&apiPreviewFailure");
    await page.getByTestId("model-call-order-row-research").locator('button[aria-haspopup="dialog"]').click();
    const dialog = page.getByRole("dialog", { name: "Research", exact: true });
    const input = dialog.getByRole("combobox", { name: "Model", exact: true });
    const writes = page.getByLabel("Model saves", { exact: true });
    await input.fill("private-research-model");
    await expect(writes).toHaveText("0");
    await input.press("Tab");
    await expect(page.getByRole("listbox")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog.getByRole("alert")).toHaveText("Model save failed");
    await expect(input).toHaveValue("private-research-model");
    const advanced = dialog.getByRole("button", { name: "Advanced options", exact: true });
    await advanced.click();
    const preview = dialog.getByRole("alert").filter({ hasText: "API preview unavailable" });
    await expect(preview).toBeVisible();
    await dialog.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(preview).toHaveCount(0);
    await advanced.click();
    await expect(advanced).toHaveAttribute("aria-expanded", "false");
    await expect(dialog.getByRole("alert")).toHaveCount(0);
    await expect(writes).toHaveText("2");
    await advanced.click();
    const context = dialog.getByRole("textbox", { name: /^Context window/ });
    await context.fill("0");
    await advanced.click();
    await expect(advanced).toHaveAttribute("aria-expanded", "true");
    await expect(context).toHaveAttribute("aria-invalid", "true");
    await expect(writes).toHaveText("2");
    await context.fill("512k");
    await advanced.click();
    await expect(advanced).toHaveAttribute("aria-expanded", "false");
    await expect(writes).toHaveText("3");
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    const row = page.getByTestId("model-call-order-row-research");
    await expect(row).toContainText("512K");
    await row.locator('button[aria-haspopup="dialog"]').click();
    await expect(input).toHaveValue("private-research-model");
    await dialog.getByRole("button", { name: "Show suggestions Model", exact: true }).click();
    await expect(page.getByRole("option", { name: "analysis-model", exact: true })).toBeVisible();
    await page.screenshot({ path: info.outputPath("catalog.png"), animations: "disabled" });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}
