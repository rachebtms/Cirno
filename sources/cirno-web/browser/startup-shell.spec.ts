import { expect, test, type Page } from "@playwright/test";

async function blockApplicationAssets(page: Page) {
  // Vite can append a timestamp query after invalidating its module graph.
  await page.route((url) => url.pathname === "/src/main.tsx"
    || /^\/assets\/index-[^/]+\.(?:js|css)$/.test(url.pathname), route => route.abort());
}

for (const width of [412, 1440]) {
  test.describe(`${width}px document startup skeleton`, () => {
    test.use({ viewport: { width, height: 922 }, reducedMotion: "reduce" });
    for (const surface of ["skills", "apps", "channels", "automations", "settings", "chat"]) {
      test(`${surface} paints before the application and stylesheet download`, async ({ page }) => {
        // Neither React nor the app stylesheet may supply this first paint.
        await blockApplicationAssets(page);
        await page.goto(`/#/${surface === "chat" ? "chat/websocket%3Aexample" : surface}`, { waitUntil: "domcontentloaded" });
        const shell = page.locator(".startup-shell");
        await expect(shell).toHaveAttribute("data-startup-surface", surface);
        await expect(shell).toHaveAttribute("aria-busy", "true");
        await expect(shell.locator(surface === "chat" ? ".startup-composer" : ".startup-page")).toBeVisible();
        const blocks = shell.locator(".startup-block:visible");
        expect(await blocks.count()).toBeGreaterThan(5);
        const box = await blocks.first().boundingBox();
        expect(box!.width).toBeGreaterThan(0);
        expect(box!.height).toBeGreaterThan(0);
        expect(await blocks.first().evaluate((element) => getComputedStyle(element).backgroundColor)).not.toBe("rgba(0, 0, 0, 0)");
        expect(await shell.getByRole("button").count()).toBe(0);
        expect(await shell.getByRole("textbox").count()).toBe(0);
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
        const status = shell.getByRole("status");
        await expect(status).toHaveText("Loading Cirno…");
        expect(await status.evaluate((element) => element.getBoundingClientRect().width)).toBe(1);
      });
    }

    test("paints the fixed launcher and settings-section alias before React", async ({ page }) => {
      await page.emulateMedia({ colorScheme: "dark" });
      await page.addInitScript(() => {
        Object.defineProperty(navigator, "languages", { get: () => ["zh-CN"] });
        Object.defineProperty(navigator, "language", { get: () => "zh-CN" });
      });
      await blockApplicationAssets(page);
      await page.goto("/#/settings?section=skills");
      const shell = page.locator(".startup-shell");
      await expect(shell).toHaveAttribute("data-startup-surface", "skills");
      await expect(shell.locator(".startup-workspace-tabs")).toBeVisible();
      await expect(shell.getByRole("status")).toHaveText("正在加载 Cirno…");
      await expect(page.locator("html")).toHaveClass(/dark/);
      const launcher = (await shell.locator(".startup-navigation").boundingBox())!;
      if (width === 1440) {
        expect(launcher.width).toBeGreaterThanOrEqual(44);
        expect(launcher.width).toBeLessThan(96);
      }
      else { expect(launcher.width).toBe(width); expect(launcher.y).toBeGreaterThan(800); }
      await expect(shell.locator(".startup-nav-row")).toHaveCount(11);
    });
  });
}
