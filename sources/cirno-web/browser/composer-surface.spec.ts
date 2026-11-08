import { seedPreviewPreferences } from "./preference-driver";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/v0/commands", route => route.fulfill({ json: { commands: [] } }));
});

for (const theme of ["light", "dark"] as const) {
  test.describe(theme, () => {
    test.beforeEach(async ({ page }) => {
      await seedPreviewPreferences(page, { language: "en", themeMode: theme });
      await page.addInitScript((theme) => {
        document.documentElement.classList.toggle("dark", theme === "dark");
      }, theme);
    });

    test("composer focus keeps the surface and actions stable", async ({ page }) => {
      await page.goto(`/browser/fixture.html?case=new-chat-skeleton${theme === "dark" ? "&dark" : ""}`);
      const surface = page.locator(".thread-composer-surface");
      await expect(surface).toBeVisible();
      const input = page.getByRole("textbox", { name: "Message input" });
      await input.blur();
      await page.getByTestId("hero-greeting").click();
      const rest = await surface.evaluate(element => getComputedStyle(element).boxShadow);
      const bounds = await surface.boundingBox();
      const footer = await page.locator(".thread-composer-footer").boundingBox();
      await input.focus();
      await expect(input).toBeFocused();
      await expect.poll(() => surface.evaluate(element => getComputedStyle(element).boxShadow)).toBe(rest);
      expect(await surface.boundingBox()).toEqual(bounds);
      expect(await page.locator(".thread-composer-footer").boundingBox()).toEqual(footer);
      await input.fill("Keep the work in focus.");
      await expect(input).toHaveValue("Keep the work in focus.");
    });

    test("drafting preserves the active Goal and its accessible details", async ({ page }) => {
      await page.goto("/browser/fixture.html?case=composer-action&goal");
      const goal = page.getByRole("status", { name: "Goal: Keep the work in focus.", exact: true });
      const input = page.getByRole("textbox", { name: "Message input" });
      await input.fill("A follow-up while this Goal runs");
      await expect(goal).toBeVisible();
      const expand = goal.getByRole("button", { name: "Show full goal", exact: true });
      await expand.click();
      const details = page.getByRole("dialog");
      await expect(details).toContainText("Keep the work in focus.");
      await page.keyboard.press("Escape");
      await expect(details).not.toBeVisible();
      await expect(expand).toBeFocused();
      await expect(input).toHaveValue("A follow-up while this Goal runs");
      await expect(goal).toBeVisible();
    });
  });
}
