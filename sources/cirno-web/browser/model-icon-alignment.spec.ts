import { expect, test } from "@playwright/test";

for (const browserName of ["chromium", "webkit"] as const) for (const width of [390, 1440]) {
  test(`${browserName}: custom provider fallback icon is centered at ${width}px`, async ({ playwright }) => {
    const browser = await playwright[browserName].launch({ headless: true });
    const page = await browser.newPage({ viewport: { width, height: 844 }, hasTouch: width < 640, isMobile: width < 640 });
    try {
      await page.goto("/browser/fixture.html?case=mobile-chat-layout&model=DeepSeek+Flash&provider=custom-api&dark=1&lang=en");
      const model = page.getByRole("button", { name: "DeepSeek Flash", exact: true });
      await expect(model).toBeVisible();
      const geometry = await model.evaluate(button => {
        const icon = button.querySelector(".model-provider-fallback svg")!.getBoundingClientRect();
        const label = button.querySelector(":scope > span:not(.model-provider-icon)")!.getBoundingClientRect();
        const tile = button.querySelector(".model-provider-icon")!.getBoundingClientRect();
        return { iconCenter: icon.top + icon.height / 2, labelCenter: label.top + label.height / 2,
          tileCenter: tile.top + tile.height / 2, iconSize: icon.height, tileSize: tile.height };
      });
      await page.screenshot({ path: test.info().outputPath("model-icon.png") });
      expect(Math.abs(geometry.iconCenter - geometry.labelCenter), JSON.stringify(geometry)).toBeLessThanOrEqual(1);
      expect(Math.abs(geometry.iconCenter - geometry.tileCenter)).toBeLessThanOrEqual(1);
    } finally { await browser.close(); }
  });
}
