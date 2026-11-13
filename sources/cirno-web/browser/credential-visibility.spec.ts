import { expect, test } from "@playwright/test";

for (const width of [390, 1280]) for (const kind of ["token", "password", "ssh"]) {
  test(`saved ${kind} has a visible eye control at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/browser/fixture.html?case=credential-visibility&lang=en&theme=dark&kind=${kind}`);
    await page.getByRole("button", { name: /Research server/ }).click();
    await page.getByRole("button", { name: "Reveal saved value" }).click();
    const value = page.locator('input[value="example-saved-secret"]');
    await expect(value).toHaveAttribute("type", "text");
    const hide = page.getByRole("button", { name: "Hide secret" });
    await expect(hide).toBeInViewport();
    const inputBox = await value.boundingBox(), eyeBox = await hide.boundingBox();
    expect(Math.abs(inputBox!.y + inputBox!.height / 2 - eyeBox!.y - eyeBox!.height / 2)).toBeLessThan(4);
    await hide.click();
    await expect(value).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "Show secret" }).click();
    await expect(value).toHaveAttribute("type", "text");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({ path: test.info().outputPath(`credential-${kind}-${width}.png`), fullPage: true });
  });
}
for (const width of [390, 1280]) test(`fixed context controls at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 });
  await page.goto('/browser/fixture.html?case=credential-visibility&lang=en&theme=dark&context');
  await expect(page.getByRole("checkbox", { name: /paper-reading/ })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: /research-review/ })).toBeDisabled();
  await expect(page.locator('textarea').filter({ hasText: 'memory/workspace/STANDARDS.md' })).toHaveValue('memory/workspace/STANDARDS.md');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  await page.screenshot({ path: test.info().outputPath(`fixed-context-${width}.png`), fullPage: true });
});
