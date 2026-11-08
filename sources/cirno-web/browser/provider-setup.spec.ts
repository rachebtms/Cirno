import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  test(`provider setup saves a connection and restores navigation focus at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: width === 390 ? "dark" : "light", reducedMotion: "reduce" });
    await page.goto("/gallery.html#component=sources%2Fcirno-web%2Fsrc%2Ffeatures%2Fsettings%2Fproviders%2FProvidersSettings.tsx");
    const preview = page.getByRole("region", { name: "Component preview", exact: true });
    const manage = preview.getByRole("button", { name: "Manage providers", exact: true });
    await manage.click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Groq", exact: true }).click();
    await expect(dialog.getByRole("heading", { name: "Groq", exact: true })).toBeVisible();
    const endpoint = dialog.getByRole("textbox", { name: "API URL", exact: true });
    await endpoint.fill("https://models.example/v1");
    await dialog.getByRole("button", { name: "Save provider", exact: true }).click();
    await dialog.getByRole("button", { name: "Groq", exact: true }).click();
    await expect(endpoint).toHaveValue("https://models.example/v1");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath("provider-setup.png") });
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(manage).toBeFocused();
  });
}
