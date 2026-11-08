import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) for (const theme of ["light", "dark"]) {
  test(`account entry recovers from a failed request at ${width}px in ${theme}`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    const requests: unknown[] = [];
    await page.route("**/v0/auth/register", async route => {
      requests.push(route.request().postDataJSON());
      await route.fulfill({ status: requests.length === 1 ? 503 : 201, json: requests.length === 1 ? { error: "request_failed" } : { ok: true } });
    });
    await page.goto(`/browser/fixture.html?case=entry&lang=en&theme=${theme}`);
    await page.getByRole("textbox", { name: /^Username/ }).fill("owner");
    await page.getByRole("textbox", { name: /^Router @name/ }).fill("snow_9");
    await page.getByLabel(/^Password/).fill("CirnoOwner!");
    await page.getByLabel(/^Confirm password/).fill("CirnoOwner!");
    await page.getByRole("button", { name: "Create account", exact: true }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByLabel(/^Password/)).toHaveValue("CirnoOwner!");
    await page.screenshot({ path: info.outputPath("entry.png"), animations: "disabled" });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole("button", { name: "Create account", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Account ready", exact: true })).toBeVisible();
    expect(requests).toEqual([{ username: "owner", password: "CirnoOwner!", router_handle: "snow_9" }, { username: "owner", password: "CirnoOwner!", router_handle: "snow_9" }]);
    expect(errors).toEqual([]);
  });
}

test("access entry keeps a secret draft while language and help change", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("/browser/fixture.html?case=entry&mode=access&lang=en&theme=dark");
  const input = page.getByLabel(/^WebUI password/);
  await expect(input).toBeFocused();
  await input.fill("keep-this-draft");
  await input.press("Shift+Tab");
  const language = page.getByRole("button", { name: /Change language/ });
  await expect(language).toBeFocused();
  await language.press("Enter");
  await expect(page.getByRole("option", { name: "English", exact: true })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(page.getByLabel(/^WebUI 密码/)).toHaveValue("keep-this-draft");
  const help = page.getByRole("button", { name: "在哪里找到密码？", exact: true });
  await help.click();
  await expect(help).toHaveAttribute("aria-expanded", "true");
  await page.screenshot({ path: info.outputPath("access.png"), animations: "disabled" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

for (const width of [390, 1440]) test(`model setup keeps both steps reachable at ${width}px`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/browser/fixture.html?case=provider-model-rebuild&setup&lang=en&theme=light");
  await expect(page.getByRole("tab", { name: "Providers", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Models", exact: true }).click();
  await page.getByRole("button", { name: "New preset", exact: true }).click();
  const draft = page.getByRole("dialog", { name: "New preset", exact: true });
  await draft.getByRole("textbox", { name: /^Preset name/ }).fill("Persistent draft");
  await draft.getByRole("button", { name: "Configure", exact: true }).click();
  await page.getByRole("dialog", { name: "OpenAI", exact: true }).getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(draft.getByRole("textbox", { name: /^Preset name/ })).toHaveValue("Persistent draft");
  await draft.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("tab", { name: "Providers", exact: true }).click();
  await page.getByRole("tab", { name: "Models", exact: true }).click();
  await expect(page.getByRole("button", { name: "New preset", exact: true })).toBeVisible();
  const row = page.getByRole("listitem").filter({ hasText: "Research" });
  expect((await row.boundingBox())!.height).toBeLessThan(width === 390 ? 180 : 100);
  await page.screenshot({ path: info.outputPath("setup.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Start chatting", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Model setup complete", exact: true })).toBeVisible();
});
