import { seedPreviewPreferences } from "./preference-driver";
import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  test.describe(`Upload settings at ${width}px`, () => {
    test.use({ viewport: { width, height: 1100 }, isMobile: width === 390, hasTouch: width === 390 });
    for (const locale of ["en", "zh-CN"]) {
      test(locale, async ({ page }, info) => {
        const zh = locale === "zh-CN";
        await seedPreviewPreferences(page, { language: locale });
        await page.addInitScript(locale => {
          document.addEventListener("DOMContentLoaded", () => document.documentElement.classList.toggle("dark", locale === "zh-CN"));
        }, locale);
        await page.goto("/browser/fixture.html?case=upload-settings");
        const group = page.getByRole("region", { name: zh ? "文件上传" : "File uploads", exact: true });
        await expect(group).toBeVisible();
        const input = group.getByRole("spinbutton", { name: zh ? "单个文件大小上限（MiB）" : "File size limit (MiB)", exact: true });
        await expect(input).toHaveValue("6");
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
        for (const field of await group.getByRole("spinbutton").all()) {
          const bounds = await field.boundingBox();
          expect(bounds!.x).toBeGreaterThanOrEqual(0);
          expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
        }
        await group.screenshot({ path: info.outputPath("upload-settings.png") });
        await input.fill("128");
        await expect(page.getByLabel("Saved settings")).toHaveText('{"server.uploads.max_file_mb":128}');
        await expect(input).toHaveValue("128");
      });
    }
  });
}
