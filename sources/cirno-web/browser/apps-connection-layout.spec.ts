import { seedPreviewPreferences } from "./preference-driver";
import { expect, test, type Locator } from "@playwright/test";

async function expectCardFits(row: Locator) {
  await expect.poll(() => row.evaluate(element => {
    const bounds = element.getBoundingClientRect();
    const controls = [...element.querySelectorAll("button, h3, [data-slot=chip]")];
    return element.scrollWidth <= element.clientWidth && controls.every(control => {
      const box = control.getBoundingClientRect();
      return box.left >= bounds.left && box.right <= bounds.right;
    });
  })).toBe(true);
}

for (const width of [314, 390, 1280]) {
  for (const locale of ["en", "zh-CN", "fr"] as const) {
    test(`MCP connection controls remain usable at ${width}px in ${locale}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 850 });
      await seedPreviewPreferences(page, { language: locale });
      await page.goto("/browser/fixture.html?case=apps&connection-layout");
      const row = page.getByRole("article", { name: "Linear", exact: true });
      const body = row.getByRole("button", { name: "Linear", exact: true });
      await expectCardFits(row);
      await body.click();
      const dialog = page.getByRole("dialog", { name: "Linear", exact: true });
      await dialog.getByRole("tab").last().click();
      await dialog.getByRole("button", { name: /^(Connect|连接|Connecter)$/ }).click();
      await expect(dialog).not.toBeVisible();
      const cancel = row.getByRole("button", { name: /^(Cancel|取消|Annuler)$/ });
      await expect(cancel).toBeEnabled();
      await expect(body).toHaveAccessibleDescription({ en: "Connecting…", "zh-CN": "正在连接…", fr: "Connexion…" }[locale]);
      await expectCardFits(row);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await body.focus();
      await page.keyboard.press("Tab");
      await expect(cancel).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(cancel).not.toBeVisible();
      await expectCardFits(row);
    });
  }
}

for (const width of [314, 1280]) {
  test(`runtime MCP connection controls fit at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 });
    await page.goto("/browser/fixture.html?case=apps&connection-layout&runtime");
    const row = page.getByRole("article", { name: "Linear", exact: true });
    await expect(row.getByRole("button", { name: "Remove", exact: true })).toBeEnabled();
    await expectCardFits(row);
  });
}
