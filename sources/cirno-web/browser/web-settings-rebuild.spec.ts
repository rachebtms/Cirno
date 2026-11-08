import { expect, test } from "@playwright/test";
for (const width of [390, 1440]) for (const theme of ["light", "dark"]) {
  test(`web configuration saves credentials and numeric edits at ${width}px in ${theme}`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/browser/fixture.html?case=web-settings-rebuild&lang=en&theme=${theme}`);
    await page.getByRole("region", { name: "Web access", exact: true }).getByRole("button", { name: "Configure", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Web access", exact: true });
    await dialog.getByRole("button", { name: /DuckDuckGo/ }).click();
    await page.getByRole("option", { name: "Brave Search", exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText("Add the required credential");
    const key = dialog.getByPlaceholder("Enter API key");
    await key.fill("fixture-search-key");
    await dialog.getByRole("button", { name: "Advanced options", exact: true }).click();
    await expect(dialog.getByPlaceholder("configured-search-key")).toBeVisible();
    const timeout = dialog.getByRole("textbox", { name: /^Search timeout/ });
    await timeout.fill("45");
    await timeout.press("Tab");
    await expect(page.getByLabel("Saved web settings")).toContainText('"timeout":45');
    await page.screenshot({ path: info.outputPath("web.png"), animations: "disabled" });
    await expect(dialog).toHaveJSProperty("scrollWidth", await dialog.evaluate(element => element.clientWidth));
    await timeout.fill("");
    await timeout.press("Tab");
    await expect(timeout).toHaveAttribute("aria-invalid", "true");
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(timeout).toHaveValue("45");
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).not.toBeVisible();
    expect(errors).toEqual([]);
  });
}
