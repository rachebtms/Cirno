import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  test.describe(`persistent actions at ${width}px`, () => {
    test.use({ viewport: { width, height: 900 }, hasTouch: width === 390, isMobile: width === 390 });
    for (const locale of ["en", "zh-CN"]) {
      for (const dark of [false, true]) {
        test(`${locale} ${dark ? "dark" : "light"}`, async ({ page }, info) => {
          const zh = locale === "zh-CN";
          await page.addInitScript(({ locale, dark }) => {
            localStorage.setItem("cirno.locale", locale);
            document.addEventListener("DOMContentLoaded", () => document.documentElement.classList.toggle("dark", dark));
          }, { locale, dark });
          await page.goto("/browser/fixture.html?case=message-actions");
          const groups = page.getByRole("group", { name: zh ? "消息操作" : "Message actions", exact: true });
          await expect(groups).toHaveCount(2);
          const user = groups.nth(0), assistant = groups.nth(1);
          await expect(user.getByRole("button", { name: zh ? "编辑消息" : "Edit message" })).toBeVisible();
          for (const group of [user, assistant]) {
            await expect(group.locator("time")).toBeVisible();
            const boxes = await group.locator("button, time").evaluateAll(elements => elements.map(element => {
              const box = element.getBoundingClientRect();
              return { x: box.x, right: box.right, center: box.y + box.height / 2 };
            }));
            for (const box of boxes) {
              expect(box.x).toBeGreaterThanOrEqual(0);
              expect(box.right).toBeLessThanOrEqual(width);
              expect(Math.abs(box.center - boxes[0].center)).toBeLessThan(2);
            }
          }
          await expect(page.locator("[data-message-block-menu]")).toHaveCount(0);
          const worked = page.locator("[data-contextual-activity-disclosure]");
          await expect(worked).toBeVisible();
          await expect(worked).toHaveAttribute("aria-expanded", "false");
          expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
          await page.screenshot({ path: info.outputPath("message-actions.png") });
          await worked.click();
          await expect(page.getByTestId("agent-activity-content")).toBeVisible();
          await worked.click();
          await user.getByRole("button", { name: zh ? "编辑消息" : "Edit message" }).click();
          await expect(page.getByLabel("Fixture action")).toHaveText("edit");
          const editor = page.getByRole("form", { name: zh ? "编辑消息" : "Edit message" });
          await expect(editor).toBeVisible();
          await expect(page.getByRole("dialog")).toHaveCount(0);
          await expect(page.locator("[data-user-text-bubble]")).toHaveCount(0);
          await expect(page.getByRole("textbox", { name: zh ? "修改后的消息" : "Edited message" })).toBeFocused();
          const box = await editor.boundingBox();
          expect(box!.width).toBeGreaterThan(width === 390 ? 300 : 650);
          expect(box!.x).toBeGreaterThanOrEqual(0);
          expect(box!.x + box!.width).toBeLessThanOrEqual(width);
          await page.screenshot({ path: info.outputPath("inline-message-editor.png") });
          await editor.getByRole("button", { name: zh ? "取消" : "Cancel", exact: true }).click();
          await expect(editor).toHaveCount(0);
          await assistant.getByRole("button", { name: zh ? "另开对话" : "New chat from here" }).click();
          await expect(page.getByLabel("Fixture action")).toHaveText("fork");
        });
      }
    }
  });
}
