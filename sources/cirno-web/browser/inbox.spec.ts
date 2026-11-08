import { expect, test } from "@playwright/test";
for (const width of [390, 844, 1440]) {
  for (const theme of ["light", "dark"]) {
    test.describe(`Inbox ${width}px ${theme}`, () => {
      test.use({ viewport: { width, height: width === 844 ? 390 : 960 }, hasTouch: width < 1000 });
      test("filters categories with an undistorted selection and a visible unread badge", async ({ page }, info) => {
        const errors: string[] = [];
        page.on("pageerror", error => errors.push(error.message));
        await page.goto(`/browser/fixture.html?case=inbox&theme=${theme}&lang=en`);
        await expect(page.getByText("Which experiment should run next?")).toBeVisible();
        for (const [name, text] of [["Actions", "Which experiment should run next?"], ["Reports", "The paper review is ready."], ["System", "Configure a model before sending your message."], ["All", "Which experiment should run next?"]]) {
          const tab = page.getByRole("tab", { name: new RegExp(`^${name}`) });
          await tab.click();
          await expect(tab).toHaveAttribute("aria-selected", "true");
          await expect(page.getByText(text)).toBeVisible();
          expect(await tab.evaluate(el => getComputedStyle(el).scale)).toBe("none");
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        }
        const badge = page.getByRole("button", { name: "Open Inbox", exact: true }).getByText("4", { exact: true });
        expect(await badge.evaluate(el => {
          const badgeRect = el.getBoundingClientRect();
          for (let ancestor = el.parentElement; ancestor; ancestor = ancestor.parentElement) {
            const style = getComputedStyle(ancestor);
            if (!/hidden|auto|scroll|clip/.test(style.overflowX + style.overflowY)) continue;
            const rect = ancestor.getBoundingClientRect();
            if (badgeRect.top < rect.top - 1 || badgeRect.left < rect.left - 1 || badgeRect.right > rect.right + 1 || badgeRect.bottom > rect.bottom + 1) return false;
          }
          return true;
        })).toBe(true);
        await page.screenshot({ path: info.outputPath("inbox.png") });
        expect(errors).toEqual([]);
      });
    });
  }
}
