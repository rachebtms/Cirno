import { seedPreviewPreferences } from "./preference-driver";
import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  test(`refresh, locked workspace and first-call context remain visible at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    await seedPreviewPreferences(page, { language: "en" });
    await page.goto("/browser/fixture.html?case=mobile-chat-layout&pending&no-context&dark");
    const refresh = page.getByRole("button", { name: "Refresh page" });
    await expect(refresh).toBeVisible();
    const refreshBox = (await refresh.boundingBox())!;
    expect(refreshBox.x + refreshBox.width).toBeLessThanOrEqual(width);
    await expect(page.getByRole("button", { name: "Switch directory" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Switch directory" })).toBeDisabled();
    await expect(page.getByTestId("composer-context-meter")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await page.screenshot({ path: testInfo.outputPath("chat.png") });
    await Promise.all([page.waitForEvent("load"), refresh.click()]);
    await expect(page.getByTestId("composer-context-meter")).toBeVisible();
  });

  test(`AI approval settings fit at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    await seedPreviewPreferences(page, { language: "en" });
    await page.goto("/browser/fixture.html?case=skeleton-additions&surface=settings&state=loaded&section=approval");
    await expect(page.getByRole("switch", { name: "Enable AI review", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Review model" })).toBeVisible();
    await expect(page.getByRole("spinbutton", { name: "Review timeout (seconds)", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await page.screenshot({ path: testInfo.outputPath("approval.png") });
  });
}
