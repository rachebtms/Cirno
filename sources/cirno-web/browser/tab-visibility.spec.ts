import { expect, test, type Locator } from "@playwright/test";

async function visibleTab(strip: Locator, name: string) {
  await expect.poll(async () => {
    const viewport = await strip.boundingBox(), tab = await strip.getByRole("tab", { name, exact: true }).boundingBox();
    return !!viewport && !!tab && tab.x >= viewport.x - 1 && tab.x + tab.width <= viewport.x + viewport.width + 1;
  }).toBe(true);
}

for (const width of [390, 1440]) {
  test(`Launcher reveals offscreen selected tabs without scrolling visible ones at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 });
    await page.goto('/browser/fixture.html?case=workspace&lang=en');
    const launcher = page.getByRole('navigation', { name: 'Launcher', exact: true });
    for (let i = 0; i < 14; i++) await launcher.getByRole('button', { name: 'Open Terminal', exact: true }).click();
    const strip = page.locator('.workbench-tabs-viewport');
    await launcher.getByRole('button', { name: 'Open @cirno', exact: true }).click();
    await visibleTab(strip, '@cirno');
    const before = await strip.evaluate(element => element.scrollLeft);
    await launcher.getByRole('button', { name: 'Open @cirno', exact: true }).click();
    await expect.poll(() => strip.evaluate(element => element.scrollLeft)).toBe(before);
    await strip.evaluate(element => { element.scrollLeft = element.scrollWidth; });
    await expect.poll(() => strip.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
    // Same destination, not a new selected ID: this must still reveal its tab.
    await launcher.getByRole('button', { name: 'Open @cirno', exact: true }).click();
    await visibleTab(strip, '@cirno');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('revealing a tab in one split group preserves the other strip position', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto('/browser/fixture.html?case=workspace&lang=en');
  const launcher = page.getByRole('navigation', { name: 'Launcher', exact: true });
  for (let i = 0; i < 6; i++) await launcher.getByRole('button', { name: 'Open Terminal', exact: true }).click();
  await page.getByRole('button', { name: 'Split view', exact: true }).click();
  for (let i = 0; i < 6; i++) await launcher.getByRole('button', { name: 'Open Files', exact: true }).click();
  const bars = page.locator('.workbench-group-bar'), right = bars.nth(1).locator('.workbench-tabs-viewport');
  await right.evaluate(element => { element.scrollLeft = 30; });
  const before = await right.evaluate(element => element.scrollLeft);
  await launcher.getByRole('button', { name: 'Open @cirno', exact: true }).click();
  await visibleTab(bars.nth(0).locator('.workbench-tabs-viewport'), '@cirno');
  await expect.poll(() => right.evaluate(element => element.scrollLeft)).toBe(before);
});
