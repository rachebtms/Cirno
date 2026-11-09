import { expect, test } from "@playwright/test";

for (const width of [390, 780, 1440]) for (const dark of [false, true]) {
  test(`system prompt additions fit a ${width}px ${dark ? "dark" : "light"} settings pane`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`/browser/fixture.html?case=skeleton-additions&surface=settings&section=personality&state=loaded&lang=en${dark ? "&dark=1" : ""}`);
    const shared = page.getByRole("textbox", { name: "Shared additional system prompt", exact: true });
    await expect(shared).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Router additional system prompt", exact: true })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Worker additional system prompt", exact: true })).toBeVisible();
    for (const editor of [shared, page.getByRole("textbox", { name: "Router additional system prompt", exact: true }), page.getByRole("textbox", { name: "Worker additional system prompt", exact: true })]) {
      const bounds = await editor.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1);
      expect(bounds!.height).toBeGreaterThan(60);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `/tmp/cirno-system-prompts-${width}-${dark ? "dark" : "light"}.png`, fullPage: true });
  });
}
