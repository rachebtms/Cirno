import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) for (const theme of ["light", "dark"]) {
  test(`first-use theme and compact model navigation at ${width}px in ${theme}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/browser/fixture.html?case=provider-model-rebuild&setupFlow&lang=en&theme=${theme}`);
    await expect(page.getByRole("heading", { name: "Make yourself at home", exact: true })).toBeVisible();
    const mode = theme === "dark" ? "Light" : "Dark";
    await page.locator("label").filter({ has: page.getByRole("radio", { name: mode, exact: true }) }).click();
    if (theme === "dark") await expect(page.locator("html")).not.toHaveClass(/dark/);
    else await expect(page.locator("html")).toHaveClass(/dark/);
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await expect(page.getByRole("tab", { name: "Providers", exact: true })).toBeVisible();
    const providers = await page.getByRole("tab", { name: "Providers", exact: true }).boundingBox();
    const models = await page.getByRole("tab", { name: "Models", exact: true }).boundingBox();
    expect(providers!.width).toBeLessThan(150);
    expect(models!.x - providers!.x - providers!.width).toBeLessThan(20);
    await page.getByRole("tab", { name: "Models", exact: true }).click();
    await expect(page.getByRole("button", { name: "New preset", exact: true })).toBeVisible();
    await page.screenshot({ path: info.outputPath("models.png"), animations: "disabled" });
    await page.getByRole("button", { name: "Back", exact: true }).click();
    await expect(page.getByRole("radio", { name: mode, exact: true })).toBeChecked();
    await page.screenshot({ path: info.outputPath("theme.png"), animations: "disabled" });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

for (const width of [1100, 1800]) test(`account content aligns with its centered settings column at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 1000 });
  await page.route("**/v0/auth/status", route => route.fulfill({ json: { enabled: true, authenticated: true, registration_required: false, username: "owner", router_handle: "cirno" } }));
  await page.goto("/browser/fixture.html?case=entry&mode=settings&lang=en&theme=dark");
  await expect(page.getByRole("textbox", { name: /^Router @name/ })).toBeVisible();
  const viewport = await page.locator(".settings-content-scroll").boundingBox();
  const column = await page.locator(".settings-content").boundingBox();
  const account = await page.locator(".account-settings").boundingBox();
  expect(Math.abs(column!.x + column!.width / 2 - viewport!.x - viewport!.width / 2)).toBeLessThan(10);
  expect(Math.abs(account!.x + account!.width / 2 - column!.x - column!.width / 2)).toBeLessThan(2);
});
