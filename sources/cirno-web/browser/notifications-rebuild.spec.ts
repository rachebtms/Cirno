import { expect, test } from "@playwright/test";
import { readPreviewPreferences } from "./preference-driver";

for (const width of [390, 1440]) for (const theme of ["light", "dark"]) {
  test(`notification categories and sound stay independent at ${width}px in ${theme}`, async ({ page, context }, info) => {
    await context.grantPermissions(["notifications"]);
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(`/browser/fixture.html?case=notifications-rebuild&lang=en&theme=${theme}`);
    const sound = page.getByRole("switch", { name: "Completion sound", exact: true });
    await expect(sound).not.toBeChecked();
    await page.getByText("Completion sound", { exact: true }).click();
    await expect(sound).toBeChecked();
    const reports = page.getByRole("switch", { name: "Reports", exact: true });
    await page.getByText("Reports", { exact: true }).click();
    await expect(reports).not.toBeChecked();
    await expect(page.getByRole("switch", { name: "Actions", exact: true })).toBeChecked();
    await expect(page.getByRole("switch", { name: "Browser notifications", exact: true })).not.toBeChecked();
    await expect.poll(async () => (await readPreviewPreferences(page)).mutedNotificationCategories).toEqual(["conversations"]);
    await page.reload();
    await expect(sound).toBeChecked(); await expect(reports).not.toBeChecked();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.classList.contains("dark"))).toBe(theme === "dark");
    await page.screenshot({ path: info.outputPath("notifications.png"), fullPage: true, animations: "disabled" });
    expect(errors).toEqual([]);
  });
}
