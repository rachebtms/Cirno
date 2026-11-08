import { expect, test } from "@playwright/test";

for (const width of [390, 1280]) {
  test(`preset summary keeps its settings visible at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/browser/fixture.html?case=skeleton-additions&surface=settings&state=loaded&section=models");

    const row = page.getByTestId("model-call-order-row-primary");
    const model = row.getByRole("button", { name: "primary openai-codex/gpt-6.1-sol 500K max", exact: true });
    const settings = row.getByText("500K", { exact: true });
    await expect(model).toBeVisible();
    await expect(settings).toBeVisible();
    await expect(row.getByText("max", { exact: true })).toBeVisible();
    expect(await settings.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

    await model.click();
    await expect(page.getByRole("dialog").getByRole("combobox", { name: "Model", exact: true })).toHaveValue("openai-codex/gpt-6.1-sol");
  });
}
