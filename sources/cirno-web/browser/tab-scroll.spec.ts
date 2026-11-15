import { expect, test, type Page } from "@playwright/test";

test.use({ hasTouch: true });
async function openStrip(page: Page, width: number) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/browser/fixture.html?case=workspace&lang=en");
  const launcher = page.getByRole("navigation", { name: "Launcher", exact: true });
  for (let i = 0; i < 14; i++) await launcher.getByRole("button", { name: "Open Terminal", exact: true }).click();
  const strip = page.locator(".workbench-tabs-viewport");
  await expect.poll(() => strip.evaluate(node => node.scrollWidth - node.clientWidth)).toBeGreaterThan(180);
  await strip.evaluate(node => { node.scrollLeft = 0; });
  return strip;
}

for (const width of [390, 1440]) test(`wheel and trackpad input scroll only horizontally at ${width}px`, async ({ page }) => {
  const strip = await openStrip(page, width);
  await strip.hover();
  await page.mouse.wheel(0, 120);
  await expect.poll(() => strip.evaluate(node => node.scrollLeft)).toBeGreaterThan(0);
  await strip.evaluate(node => { node.scrollLeft = 0; });
  await page.mouse.wheel(90, 0);
  await expect.poll(() => strip.evaluate(node => node.scrollLeft)).toBeGreaterThan(0);
  expect(await strip.evaluate(node => node.scrollTop)).toBe(0);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  const styles = await strip.evaluate(node => {
    const style = getComputedStyle(node);
    return { y: style.overflowY, touch: style.touchAction, overscroll: style.overscrollBehavior };
  });
  expect(styles).toEqual({ y: "hidden", touch: "pan-x pinch-zoom", overscroll: "none" });
});

test("touch pans horizontally and rejects vertical panning without reordering", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "Native touch input uses Chromium's device input channel.");
  const strip = await openStrip(page, 390);
  const bounds = (await strip.boundingBox())!;
  const tabs = await strip.locator("[data-reorder-id]").evaluateAll(nodes => nodes.map(node => (node as HTMLElement).dataset.reorderId));
  const device = await page.context().newCDPSession(page);
  const x = bounds.x + bounds.width - 25, y = bounds.y + bounds.height / 2;
  await device.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] });
  for (let step = 1; step <= 6; step++) await device.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: x - step * 25, y }] });
  await device.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await expect.poll(() => strip.evaluate(node => node.scrollLeft)).toBeGreaterThan(0);
  await device.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] });
  for (let step = 1; step <= 6; step++) await device.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y: y + step * 25 }] });
  await device.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  expect(await strip.evaluate(node => node.scrollTop)).toBe(0);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  expect(await strip.locator("[data-reorder-id]").evaluateAll(nodes => nodes.map(node => (node as HTMLElement).dataset.reorderId))).toEqual(tabs);
  await device.detach();
});
