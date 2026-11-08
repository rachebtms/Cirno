import { seedPreviewPreferences } from "./preference-driver";
import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  for (const locale of ["en", "zh-CN"]) {
    test.describe(`Usage details ${width}px ${locale}`, () => {
      test.use({ viewport: { width, height: 1100 }, isMobile: width === 390, hasTouch: width === 390 });
      test("click or tap pins details until outside click or Escape", async ({ page }, info) => {
        await seedPreviewPreferences(page, { language: locale });
        await page.addInitScript(locale => {
          document.addEventListener("DOMContentLoaded", () => document.documentElement.classList.toggle("dark", locale === "zh-CN"));
        }, locale);
        await page.goto("/browser/fixture.html?case=usage-chart");
        const bars = page.locator('button[role="img"]');
        await expect(bars).toHaveCount(2);
        for (let i = 0; i < 2; i++) {
          await bars.nth(i).click();
          const detail = page.getByRole("dialog").last();
          await expect(detail).toBeVisible();
          await page.mouse.move(5, 5);
          // Exercise the original touch/hover close race after the pointer leaves.
          await page.waitForTimeout(650);
          await expect(detail).toBeVisible();
          const box = (await detail.boundingBox())!;
          expect(box.x).toBeGreaterThanOrEqual(0);
          expect(box.x + box.width).toBeLessThanOrEqual(width);
          await page.screenshot({ path: info.outputPath(`usage-details-${i}.png`) });
          if (i === 0) await page.getByRole("button", { name: "Outside chart" }).click();
          else await page.keyboard.press("Escape");
          await expect(page.getByRole("dialog")).toHaveCount(0);
        }
      });
    });
  }
}
