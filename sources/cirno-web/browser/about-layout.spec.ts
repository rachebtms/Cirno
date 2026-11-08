import { seedPreviewPreferences } from "./preference-driver";
import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  test(`About centers its wordmark at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 960 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await seedPreviewPreferences(page, { language: "en" });
    await page.goto("/browser/fixture.html?case=skeleton-additions&surface=settings&state=loaded&section=about");
    const title = page.getByRole("heading", { name: "Cirno", exact: true });
    await expect(title).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    const mark = page.locator('img[src="/brand/cirno_snowflake_mark.svg"]');
    const text = (await title.boundingBox())!;
    const logo = (await mark.boundingBox())!;
    expect(Math.abs(text.x + text.width / 2 - logo.x - logo.width / 2)).toBeLessThan(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await page.screenshot({ path: testInfo.outputPath("about.png") });
  });
}
