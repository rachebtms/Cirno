import { expect, test } from "@playwright/test";

// Desktop engines cannot open an iOS keyboard. Drive its visual viewport
// contract without changing the layout viewport, as WebKit does on iPhone.
for (const browserName of ["chromium", "webkit"] as const)
for (const surface of ["register", "login", "chat"]) test(`${browserName}: keyboard keeps ${surface} input visible`, async ({ playwright }) => {
  const browser = await playwright[browserName].launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  try {
    await page.addInitScript(() => {
      const viewport = Object.assign(new EventTarget(), { height: 844, width: 390, offsetTop: 0, offsetLeft: 0, scale: 1 });
      Object.defineProperty(window, "visualViewport", { value: viewport });
      Object.assign(window, { resizeKeyboard(height: number, top = 0, scale = 1) {
        Object.assign(viewport, { height, offsetTop: top, scale });
        viewport.dispatchEvent(new Event("resize"));
      } });
    });
    await page.goto(`/browser/fixture.html?case=keyboard-viewport&surface=${surface}&mode=${surface}&lang=en&theme=dark`);
    const input = surface === "chat" ? page.locator("textarea").first() : page.locator('input[name="password"]');
    await input.fill("Retained draft 中文");
    await input.focus();
    await page.evaluate(() => (window as unknown as { resizeKeyboard: (height: number, top: number, scale: number) => void }).resizeKeyboard(390, 70, 1.0000001));
    await expect.poll(() => page.locator("#root").evaluate(el => el.getBoundingClientRect().height)).toBe(390);
    await expect.poll(async () => { const box = await input.boundingBox(); return !!box && box.y >= 70 && box.y + box.height <= 460; }).toBe(true);
    await expect(input).toBeFocused();
    await expect(input).toHaveValue("Retained draft 中文");
    expect(await input.evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
    await page.screenshot({ path: test.info().outputPath(`${surface}-keyboard.png`) });
    await page.evaluate(() => (window as unknown as { resizeKeyboard: (height: number) => void }).resizeKeyboard(844));
    await expect.poll(() => page.locator("#root").evaluate(el => el.getBoundingClientRect().height)).toBe(844);
    await expect(input).toHaveValue("Retained draft 中文");
  } finally { await browser.close(); }
});
