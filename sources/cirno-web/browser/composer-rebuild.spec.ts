import { expect, test } from "@playwright/test";

for (const width of [314, 390, 1440]) for (const theme of ["light", "dark"]) {
  test(`shared composer editing and actions at ${width}px in ${theme}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const heights: number[] = [];
    for (const variant of ["hero", "thread"]) {
      await page.goto(`/browser/fixture.html?case=composer-action&composerVariant=${variant}&models&lang=en&theme=${theme}`);
      const input = page.getByRole("textbox", { name: "Message input" });
      await expect(input).toBeVisible();
      heights.push((await page.locator(".composer-surface").boundingBox())!.height);
      await input.fill("Keep this question while switching models.");
      const model = page.getByRole("button", { name: "Preview", exact: true });
      await model.hover();
      await expect(page.getByRole("tooltip")).toContainText("research-small");
      await expect(page.getByRole("tooltip")).toContainText("Research provider");
      await page.screenshot({ path: testInfo.outputPath(`model-hint-${variant}.png`), animations: "disabled" });
      await model.click();
      await expect(page.locator('[role="tooltip"]')).toHaveCount(0);
      await page.getByRole("menuitemradio", { name: /^Analysis/ }).click();
      await expect(input).toHaveValue("Keep this question while switching models.");
      await expect(page.getByRole("button", { name: "Analysis", exact: true })).toBeVisible();
      await page.locator('input[type="file"]').setInputFiles({ name: "research-notes.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\nnotes") });
      const attachment = page.getByRole("button", { name: "research-notes.pdf", exact: true });
      await attachment.click();
      const details = page.getByRole("dialog", { name: "research-notes.pdf", exact: true });
      await expect(details).toBeVisible();
      await expect(details).toContainText("research-notes.pdf");
      await expect(page.locator('[role="tooltip"]')).toHaveCount(0);
      await page.keyboard.press("Escape");
      await expect(details).not.toBeVisible();
      await expect(attachment).toBeFocused();
      const remove = page.getByRole("button", { name: "Remove attachment" });
      const bounds = (await remove.boundingBox())!;
      expect(bounds.width).toBeGreaterThanOrEqual(44); expect(bounds.height).toBeGreaterThanOrEqual(44);
      await remove.click(); await expect(page.getByTestId("composer-chip")).toHaveCount(0);
      await expect(input).toHaveValue("Keep this question while switching models.");
      await page.screenshot({ path: testInfo.outputPath(`${variant}.png`), animations: "disabled" });
      await page.getByRole("button", { name: "Send message", exact: true }).click();
      await expect(page.getByLabel("Execution status")).toHaveText("Working");
      await page.getByRole("button", { name: "Stop response", exact: true }).click();
      await expect(page.getByLabel("Execution status")).toHaveText("Stop requested");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    expect(heights[0]).toEqual(heights[1]);
    expect(errors).toEqual([]);
  });
}
