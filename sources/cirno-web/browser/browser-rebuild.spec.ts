import { expect, test } from "@playwright/test";
for (const width of [390, 1440]) for (const theme of ["light", "dark"]) {
  test(`browser navigation and independent tabs at ${width}px in ${theme}`, async ({ page }) => {
    let reads = 0;
    await page.setViewportSize({ width, height: 900 });
    await page.route("https://example.com/research", route => { reads++; return route.fulfill({ contentType: "text/html", body: "<h1>Research document</h1>" }); });
    await page.goto(`/browser/fixture.html?case=workspace&lang=en&theme=${theme}`);
    await page.getByRole("button", { name: "Open Browser", exact: true }).click();
    await page.getByRole("textbox", { name: "Website address", exact: true }).fill("example.com/research");
    await page.getByRole("button", { name: "Go", exact: true }).click();
    await expect(page.frameLocator("iframe").getByRole("heading", { name: "Research document" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open in browser" })).toHaveAttribute("href", "https://example.com/research");
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await expect.poll(() => reads).toBe(2);
    await page.getByRole("button", { name: "Open Browser", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "Website address", exact: true })).toHaveValue("");
    const tabs = page.getByRole("tab", { name: "Browser", exact: true });
    await expect(tabs).toHaveCount(2); await tabs.first().click();
    await expect(page.getByRole("textbox", { name: "Website address", exact: true })).toHaveValue("https://example.com/research");
    await page.screenshot({ path: test.info().outputPath("browser.png"), animations: "disabled" });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
