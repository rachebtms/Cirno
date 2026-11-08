import { updatePreviewPreferences } from "./preference-driver";
import { expect, test } from "@playwright/test";

for (const theme of ["light", "dark"]) {
  for (const logos of ["shown", "hidden"]) {
    test(`unbranded Apps initials stay readable in ${theme} mode with logos ${logos}`, async ({ page }) => {
      await page.route("**/missing-app-icon.svg", (route) => route.fulfill({ status: 404, body: "" }));
      await page.goto(`/browser/fixture.html?case=apps&logos=${logos}`);
      await updatePreviewPreferences(page, { themeMode: theme as "light" | "dark" });

      for (const initials of ["CW", "TM"]) {
        const icon = page.locator(".catalog-logo").filter({ hasText: initials });
        await expect(icon).toBeVisible();
        const contrast = await icon.evaluate((element) => {
          const style = getComputedStyle(element);
          const luminance = (color: string) => {
            const canvas = document.createElement("canvas");
            canvas.width = canvas.height = 1;
            const context = canvas.getContext("2d")!;
            context.fillStyle = color;
            context.fillRect(0, 0, 1, 1);
            const channels = Array.from(context.getImageData(0, 0, 1, 1).data).slice(0, 3).map((value) => {
              const channel = value / 255;
              return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
            });
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
          };
          const foreground = luminance(style.color);
          const background = luminance(style.backgroundColor);
          return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
        });
        expect(contrast).toBeGreaterThanOrEqual(4.5);
        await expect(icon).toHaveCSS("width", "36px");
        await expect(icon).toHaveCSS("height", "36px");
      }
      const branded = page.locator(".catalog-logo").filter({ hasText: "BE" });
      await expect(branded).toHaveCSS("color", "rgb(94, 106, 210)");
    });
  }
}
