import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  test.describe(`Question rewind ${width}px`, () => {
    test.use({ viewport: { width, height: 900 }, isMobile: width === 390, hasTouch: width === 390 });
    test("restores unanswered questions in order after editing history", async ({ page }, info) => {
      await page.addInitScript(dark => {
        document.addEventListener("DOMContentLoaded", () => document.documentElement.classList.toggle("dark", dark));
      }, width === 390);
      await page.goto("/browser/fixture.html?case=user-questions");
      const first = page.getByRole("button", { name: /^CSV with/ });
      await expect(first).toBeVisible();
      await first.click();
      await expect(page.getByText("Which language should the report use?")).toBeVisible();
      await page.getByRole("button", { name: "Rewind answer" }).click();
      await expect(first).toBeVisible();
      await expect(page.getByText("Which language should the report use?")).toBeHidden();
      const card = page.getByRole("region", { name: "A question for you" });
      const bounds = (await card.boundingBox())!;
      expect(bounds.x).toBeGreaterThanOrEqual(0);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
      expect(bounds.y + bounds.height).toBeLessThanOrEqual(901);
      await expect(page.getByRole("textbox", { name: "Other" })).toBeVisible();
      await page.screenshot({ path: info.outputPath("questions-after-rewind.png") });
    });
  });
}
