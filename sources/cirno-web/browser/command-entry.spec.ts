import { expect, test } from "@playwright/test";
import { seedPreviewPreferences } from "./preference-driver";

for (const width of [390, 1280]) test(`all slash commands remain reachable with keyboard and scroll at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 950 });
  await seedPreviewPreferences(page, { language: "en", themeMode: "dark" });
  await page.goto("/browser/fixture.html?case=composer-action&commands=1");
  const input = page.getByRole("textbox", { name: "Message input" });
  await input.fill("/");
  const menu = page.getByRole("listbox", { name: "Slash commands" });
  await expect(menu.getByRole("option")).toHaveCount(13);
  const last = menu.getByRole("option").last();
  for (let n = 0; n < 12; n++) await input.press("ArrowDown");
  await expect(last).toHaveAttribute("aria-selected", "true");
  const item = (await last.boundingBox())!, bounds = (await menu.boundingBox())!;
  expect(item.y).toBeGreaterThanOrEqual(bounds.y);
  expect(item.y + item.height).toBeLessThanOrEqual(bounds.y + bounds.height);
  await page.screenshot({ path: `/tmp/cirno-command-menu-${width}.png` });
  await input.press("Tab");
  await expect(input).toHaveValue("/stop");
  await input.fill("/dream-r");
  await expect(menu.getByRole("option")).toHaveCount(1);
  await input.press("Tab");
  await expect(input).toHaveValue("/dream-restore ");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
