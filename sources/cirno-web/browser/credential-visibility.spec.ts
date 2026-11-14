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
  await page.route('**/v0/webui/skills/*', route => {
    const name = route.request().url().split('/').at(-1)!;
    return route.fulfill({ json: { name, description: 'Scientific research workflow', source: 'home',
      available: true, enabled: true, always: name === 'research-review', raw_markdown: '# Research workflow',
      requirements: { bins: [], env: [], missing_bins: [], missing_env: [] }, install_options: [] } });
  });
  await expect(page.getByRole("heading", { name: "Fixed Skills" })).toHaveCount(0);
  await expect(page.locator('textarea').filter({ hasText: 'memory/workspace/STANDARDS.md' })).toHaveValue('memory/workspace/STANDARDS.md');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  await page.getByRole('button', { name: 'Open details for paper-reading', exact: true }).click();
  const detail = page.getByRole('dialog', { name: 'paper-reading', exact: true });
  await expect(detail.getByRole('switch', { name: 'Always inject', exact: true })).toBeChecked();
  const label = detail.getByText('Always inject', { exact: true });
  const labelBox = await label.boundingBox(), controlBox = await detail.locator('.interface-toggle')
    .filter({ hasText: 'Always inject' }).locator('[data-slot="switch-control"]').boundingBox();
  expect(Math.abs(labelBox!.y + labelBox!.height / 2 - controlBox!.y - controlBox!.height / 2)).toBeLessThan(5);
  await expect(detail).toHaveCSS('opacity', '1');
  await page.screenshot({ path: test.info().outputPath(`fixed-context-${width}.png`), fullPage: true, animations: 'disabled' });
  await detail.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'Open details for research-review', exact: true }).click();
  const declared = page.getByRole('dialog', { name: 'research-review', exact: true }).getByRole('switch', { name: 'Always inject', exact: true });
  await expect(declared).toBeChecked();
  await expect(declared).toBeDisabled();
});
