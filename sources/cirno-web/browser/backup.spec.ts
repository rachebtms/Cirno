import { seedPreviewPreferences } from "./preference-driver";
import { expect, test } from "@playwright/test";

for (const locale of ["en", "zh-CN"]) for (const width of [390, 1280]) {
  test(`backup and Node details in ${locale} at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await seedPreviewPreferences(page, { language: locale });
    await page.goto("/browser/fixture.html?case=backup");
    const chinese = locale === "zh-CN";
    await expect(page.getByRole("checkbox", { name: "/data/cirno/state/cli/config/tea" })).toBeDisabled();
    await expect(page.getByRole("checkbox", { name: "/workspaces/research/long-term-experiment-and-evidence" })).toBeChecked();
    await expect(page.getByRole("button", { name: chinese ? "导出备份" : "Export backup" })).toBeEnabled();
    const node = page.getByRole("region", { name: "Node execution" });
    await node.getByRole("button", { name: chinese ? "展开详情" : "Expand step" }).click();
    await expect(page.getByTestId("activity-step-details")).toContainText("experiment.py --seed 42");
    await expect(page.getByTestId("activity-step-details")).toContainText("epoch 2");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({ path: test.info().outputPath(`backup-${locale}-${width}.png`), fullPage: true });
    await page.locator('input[type="file"]').setInputFiles({ name: "backup.tar.gz", mimeType: "application/gzip", buffer: Buffer.from("fixture") });
    await expect(page.getByRole("dialog")).toBeVisible();
    const restore = page.getByRole("button", { name: chinese ? "恢复并重启" : "Restore and restart" });
    await expect(restore).toBeVisible();
    const box = await restore.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(width);
    await page.getByRole("dialog").evaluate(async (dialog) => {
      await Promise.all(dialog.getAnimations({ subtree: true }).map((animation) => animation.finished));
    });
    await page.screenshot({ path: test.info().outputPath(`restore-${locale}-${width}.png`), fullPage: true });
    await restore.click();
    await expect(page.getByRole("status", { name: "Restarted" })).toHaveText("true");
  });
}
