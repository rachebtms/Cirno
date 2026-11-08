import { seedPreviewPreferences } from "./preference-driver";
import { expect, test } from "@playwright/test";

for (const width of [1440, 390]) {
  for (const variant of ["thread", "hero"]) {
    for (const notice of ["recovery", "stream", "fallback"]) {
      test(`${notice} aligns with ${variant} composer at ${width}px`, async ({ page }, info) => {
        await page.setViewportSize({ width, height: 1000 });
        await page.emulateMedia({ reducedMotion: "reduce" });
        await seedPreviewPreferences(page, { language: width === 390 ? "zh-CN" : "en", readingTextSize: "large", themeMode: variant === "hero" ? "dark" : "light" });
        await page.addInitScript(dark => {
          document.addEventListener("DOMContentLoaded", () => document.documentElement.classList.toggle("dark", dark));
        }, variant === "hero");
        await page.goto(`/browser/fixture.html?case=chat-failure&notice=${notice}&variant=${variant}`);
        const alert = notice === "recovery" ? page.getByRole("alert") : page.locator(".thread-composer-notice");
        const composer = page.locator(".thread-composer-surface");
        await expect(alert).toBeVisible();
        await expect(composer).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
        if (notice === "recovery") {
          await expect(page.locator(".thread-composer-notice")).toHaveCount(0);
          const noteBox = (await alert.boundingBox())!;
          const inputBox = (await composer.boundingBox())!;
          expect(Math.abs(noteBox.x - inputBox.x)).toBeLessThan(1);
          expect(Math.abs(noteBox.width - inputBox.width)).toBeLessThan(1);
          await expect(alert).toContainText(width === 390 ? "模型提供商验证失败" : "Model provider authorization failed");
          const resume = composer.getByRole("button", { name: width === 390 ? "继续" : "Continue", exact: true });
          await expect(resume).toBeInViewport({ ratio: 1 });
          await expect(resume).toHaveClass(/composer-primary-action/);
          await page.screenshot({ path: info.outputPath("composer-recovery.png") });
          await resume.click();
          await expect(alert).toBeHidden();
          await expect(page.getByLabel("Fixture action")).toHaveText("continued");
        } else {
          await alert.getByRole("button").last().click();
          await expect(alert).toBeHidden();
          await expect(page.getByLabel("Fixture action")).toHaveText("dismissed");
        }
      });
    }
  }
}

for (const width of [1440, 390]) {
  for (const size of ["small", "standard", "large"] as const) {
    test(`image and quote retain the responsive message actions: ${size}, ${width}px`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 1000 });
      await seedPreviewPreferences(page, { language: width === 390 ? "zh-CN" : "en", readingTextSize: size });
      await page.goto("/browser/fixture.html?case=chat-failure");
      const image = page.getByAltText("Failure screenshot");
      await expect(image).toBeVisible();
      await expect(page.getByText("Earlier context / 之前的上下文")).toBeVisible();
      const bubble = page.locator("[data-user-text-bubble]");
      const text = bubble.locator("p");
      const actions = page.locator("[data-message-actions]");
      const fontSize = { small: 14, standard: 16, large: 18 }[size];
      await expect(text).toHaveCSS("font-size", `${fontSize}px`);
      await expect(actions).toBeVisible();
      const bubbleBox = (await bubble.boundingBox())!;
      const actionsBox = (await actions.boundingBox())!;
      const imageBox = (await image.boundingBox())!;
      expect(imageBox.y + imageBox.height).toBeLessThan(bubbleBox.y);
      expect(actionsBox.y).toBeGreaterThanOrEqual(bubbleBox.y + bubbleBox.height);
      await expect(actions.getByRole("button", { name: width === 390 ? "复制" : "Copy", exact: true })).toBeInViewport({ ratio: 1 });
      await expect(actions.locator("time")).toBeVisible();
      await expect(page.locator("[data-message-block-menu]")).toHaveCount(0);
      await page.screenshot({ path: info.outputPath("message-actions.png") });
    });
  }
}
