import { expect, test, type Locator, type Page } from "@playwright/test";

async function drag(page: Page, source: Locator, target: Locator, touch: boolean) {
  const from = (await source.boundingBox())!, to = (await target.boundingBox())!;
  const a = { x: from.x + from.width / 2, y: from.y + from.height / 2 };
  const b = { x: to.x + to.width / 2, y: to.y + to.height / 2 };
  if (touch) {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [a] });
    await page.waitForTimeout(400);
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [b] });
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await cdp.detach();
  } else {
    await page.mouse.move(a.x, a.y);
    await page.mouse.down();
    await page.mouse.move(b.x, b.y, { steps: 8 });
    await page.mouse.up();
  }
}
for (const width of [390, 1440]) test.describe(`Workbench ordering at ${width}px`, () => {
  test.use({ viewport: { width, height: 960 }, hasTouch: width === 390, isMobile: width === 390 });
  test("singletons, independent panels and pointer ordering retain their owners", async ({ page }) => {
    await page.goto("/browser/fixture.html?case=workspace&lang=en");
    const launcher = page.getByRole("navigation", { name: "Launcher", exact: true });
    await launcher.getByRole("button", { name: "Open Credentials", exact: true }).click();
    await launcher.getByRole("button", { name: "Open Credentials", exact: true }).click();
    await expect(page.getByRole("tab", { name: "Credentials", exact: true })).toHaveCount(1);
    await launcher.getByRole("button", { name: "Open Conversations", exact: true }).click();
    await launcher.getByRole("button", { name: "Open Conversations", exact: true }).click();
    await expect(page.getByRole("tab", { name: "Conversations", exact: true })).toHaveCount(1);
    const list = page.getByRole("tablist", { name: "Workspace tabs" });
    const before = await list.getByRole("tab").evaluateAll(tabs => tabs.map(tab => tab.getAttribute("data-reorder-id")));
    await drag(page, list.getByRole("tab").nth(1), list.getByRole("tab").first(), width === 390);
    await expect.poll(() => list.getByRole("tab").evaluateAll(tabs => tabs.map(tab => tab.getAttribute("data-reorder-id")))).toEqual([before[1], before[0], before[2]]);
    const firstTab = list.getByRole("tab").first();
    await firstTab.focus();
    await page.keyboard.press("Alt+ArrowRight");
    await expect.poll(() => list.getByRole("tab").evaluateAll(tabs => tabs.map(tab => tab.getAttribute("data-reorder-id")))).toEqual(before);
    const selectedBeforeLauncherDrag = await list.getByRole("tab", { selected: true }).getAttribute("aria-label");
    const strip = launcher.locator("[data-launcher-scroll]");
    await strip.evaluate(element => { element.scrollLeft = 0; element.scrollTop = 0; });
    await drag(page, strip.locator('[data-reorder-id="cirno"]'), strip.locator('[data-reorder-id="conversations"]'), width === 390);
    await expect.poll(() => strip.locator("[data-reorder-id]").evaluateAll(items => items.slice(0, 2).map(item => item.getAttribute("data-reorder-id")))).toEqual(["conversations", "cirno"]);
    await expect(list.getByRole("tab", { selected: true })).toHaveAttribute("aria-label", selectedBeforeLauncherDrag!);
    await page.reload();
    await expect(strip.locator("[data-reorder-id]").first()).toHaveAttribute("data-reorder-id", "conversations");
    await expect(page.getByRole("tab", { name: "Credentials", exact: true })).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `/tmp/cirno-review79-ordering-${width}.png`, fullPage: true });
  });
});
