import { readPreviewPreferences } from "./preference-driver";
import { expect, test, type Page } from "@playwright/test";

async function settlePalette(page: Page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise(requestAnimationFrame);
    await Promise.all(document.getAnimations().filter(animation => animation.effect?.getTiming().iterations !== Infinity)
      .map(animation => animation.finished.catch(() => {})));
  });
}

for (const width of [1440, 390]) {
  for (const initial of ["light", "dark"] as const) {
    for (const reducedMotion of ["reduce", "no-preference"] as const) {
      test(`${width}px ${initial} ${reducedMotion}: changes the shared palette without losing drafts or layout`, async ({ page }) => {
        await page.setViewportSize({ width, height: 844 });
        await page.emulateMedia({ reducedMotion });
        await page.goto(`/browser/fixture.html?case=theme-toggle&chat&theme=${initial}`);
        const toggle = page.getByRole("button", { name: "Toggle theme from header", exact: true });
        const input = page.getByRole("textbox");
        const icon = toggle.locator("svg");
        await expect(icon).toHaveAttribute("data-theme", initial);
        await input.fill("Keep this draft while changing theme");
        const inputBox = await input.boundingBox();
        const selectors = [".thread-workspace", ".workbench", ".thread-composer-surface", "nav"];
        const paint = () => page.evaluate(targets => targets.map(selector => {
          const style = getComputedStyle(document.querySelector(selector)!);
          return { background: style.backgroundColor, color: style.color };
        }), selectors);
        await settlePalette(page);
        const before = await paint();
        await toggle.focus();
        await page.keyboard.press("Space");
        const next = initial === "light" ? "dark" : "light";
        await expect(icon).toHaveAttribute("data-theme", next);
        await expect.poll(paint).not.toEqual(before);
        await settlePalette(page);
        const after = await paint();
        for (const [index, selector] of selectors.entries()) {
          expect(after[index], selector).not.toEqual(before[index]);
          expect(after[index].background, selector).not.toBe("rgba(0, 0, 0, 0)");
        }
        await expect(input).toHaveValue("Keep this draft while changing theme");
        expect(await input.boundingBox()).toEqual(inputBox);
        await expect(toggle).toBeFocused();
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
        if (reducedMotion === "reduce") {
          expect(await icon.evaluate(node => node.getAnimations({ subtree: true }).length)).toBe(0);
        }
        await expect.poll(() => readPreviewPreferences(page).then(values => values.themeMode)).toBe(next);
        await page.screenshot({ path: test.info().outputPath(`theme-${width}-${next}-${reducedMotion}.png`) });
        await page.reload();
        await expect(icon).toHaveAttribute("data-theme", next);
        await settlePalette(page);
        expect(await paint()).toEqual(after);
      });
    }
  }
}

test("Settings navigation retains its selected section through reduced motion and theme changes", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 844 });
  await page.goto("/browser/fixture.html?case=theme-toggle&selection");
  const overview = page.getByRole("button", { name: "Overview", exact: true });
  const appearance = page.getByRole("button", { name: "Appearance", exact: true });
  await expect(overview).toHaveAttribute("aria-current", "page");
  await appearance.focus();
  await page.keyboard.press("Space");
  await expect(appearance).toHaveAttribute("aria-current", "page");
  await expect(overview).not.toHaveAttribute("aria-current");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.getByRole("button", { name: "Toggle theme from header", exact: true }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(appearance).toHaveAttribute("aria-current", "page");
  await overview.click();
  await expect(overview).toHaveAttribute("aria-current", "page");
});
