import { expect, test } from "@playwright/test";
import { seedPreviewPreferences } from "./preference-driver";

for (const language of ["en", "zh-CN"]) {
  for (const width of [390, 1280]) {
    test(`unified context consolidation in ${language} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await seedPreviewPreferences(page, { language });
      await page.goto("/browser/fixture.html?case=idle-compaction");
      const chinese = language === "zh-CN";
      await expect(page.locator('[data-settings-section="consolidation"]')).toBeVisible();
      if (width >= 1024) await expect(page.getByRole("heading", { name: chinese ? "上下文整理" : "Context consolidation", exact: true })).toBeVisible();
      const learning = page.getByRole("switch", { name: chinese ? "整理时保存经验" : "Learn during consolidation" });
      await expect(learning).toBeChecked();
      await expect(page.getByRole("spinbutton", { name: chinese ? "每次最多更新数" : "Maximum updates per consolidation" })).toHaveValue("8");
      await expect(page.getByRole("spinbutton", { name: chinese ? "额外参考内容上限（字符）" : "Additional reference budget (characters)" })).toHaveValue("16000");
      await expect(page.getByRole("spinbutton", { name: chinese ? "整理输出预算（Token）" : "Consolidation output budget (tokens)" })).toHaveValue("8192");
      await expect(page.getByText(/Dream|上下文压缩/)).toHaveCount(0);
      await learning.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/cirno-consolidation-${language}-${width}.png`, fullPage: true });
      await page.getByText(chinese ? "整理时保存经验" : "Learn during consolidation", { exact: true }).click();
      await expect(learning).not.toBeChecked();
      await expect(page.getByRole("spinbutton", { name: chinese ? "每次最多更新数" : "Maximum updates per consolidation" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: chinese ? "保存更改" : "Save changes", exact: true })).toHaveCount(0);
      // Turning off learning leaves the task-checkpoint controls available.
      await expect(page.getByRole("spinbutton", { name: chinese ? "整理输出预算（Token）" : "Consolidation output budget (tokens)" })).toHaveCount(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });
  }
}
