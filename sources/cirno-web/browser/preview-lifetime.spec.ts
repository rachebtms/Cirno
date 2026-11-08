import { expect, test } from "@playwright/test";
for (const width of [390, 1440]) test(`a closed temporary preview stays closed across immediate tab switches at ${width}px`, async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.setViewportSize({ width, height: 900 });
  await page.goto(`/browser/fixture.html?case=preview-lifetime&lang=en&theme=${width === 390 ? "dark" : "light"}`);
  await page.getByRole("button", { name: "Open attached file" }).click();
  await expect(page.getByText("Retained temporary file preview", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close notes.txt" }).click();
  await page.getByRole("button", { name: "Other tab" }).click();
  await page.getByRole("button", { name: "Temporary tab" }).click();
  await expect(page.getByTestId("file-preview-panel")).toHaveCount(0);
  await page.getByRole("button", { name: "Open attached file" }).click();
  await expect(page.getByText("Retained temporary file preview", { exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath(`temporary-preview-${width}.png`), animations: "disabled" });
  expect(errors).toEqual([]);
});
