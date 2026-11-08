import { expect, test, type Page } from "@playwright/test";

async function openAuthorization(page: Page, width: number, flag: string) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(`/browser/fixture.html?case=provider-model-rebuild&lang=en&theme=dark&oauth&${flag}`);
  await page.getByRole("button", { name: "Manage providers", exact: true }).click();
  await page.getByRole("button", { name: "Add provider", exact: true }).click();
  const search = page.getByRole("searchbox", { name: "Search providers", exact: true });
  if (width < 640) await expect(search).not.toBeFocused();
  else await expect(search).toBeFocused();
  await page.getByRole("option", { name: "GitHub Copilot", exact: true }).click();
  await page.getByRole("dialog", { name: "GitHub Copilot", exact: true }).getByRole("button", { name: "Sign in", exact: true }).click();
}

for (const width of [390, 1440]) {
  test(`authorization failure can retry without losing its flow at ${width}px`, async ({ page }, info) => {
    const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
    await openAuthorization(page, width, "oauthPollFailure");
    const notice = page.getByRole("alert").filter({ hasText: "Authorization service unavailable" });
    await expect(notice).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Device code", exact: true })).toHaveValue("FIXT-URE1");
    await page.screenshot({ path: info.outputPath("authorization-error.png"), animations: "disabled" });
    await notice.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "GitHub Copilot", exact: true })).toBeFocused();
    expect(errors).toEqual([]);
  });

  test(`cancellation failure stays open for retry at ${width}px`, async ({ page }, info) => {
    await openAuthorization(page, width, "oauthCancelFailure");
    const authorization = page.getByRole("dialog", { name: "Sign in · GitHub Copilot", exact: true });
    await authorization.getByRole("button", { name: "Close", exact: true }).click();
    const notice = authorization.getByRole("alert");
    await expect(notice).toContainText("Authorization cancellation unavailable");
    await expect(authorization.getByRole("button", { name: "Open GitHub", exact: true })).toBeDisabled();
    await page.screenshot({ path: info.outputPath("cancel-error.png"), animations: "disabled" });
    await notice.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(authorization).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "GitHub Copilot", exact: true }).getByRole("button", { name: "Sign in", exact: true })).toBeEnabled();
  });

  test(`a released editor's error remains visible and actionable at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/browser/fixture.html?case=provider-model-rebuild&lang=en&theme=dark&oauthReleaseFailure");
    await page.getByRole("button", { name: "Release inactive sign-in", exact: true }).click();
    const notice = page.locator('[data-slot="toast"]');
    await expect(notice).toContainText("Authorization cancellation unavailable");
    await expect(notice).toBeInViewport({ ratio: 1 });
    await page.screenshot({ path: info.outputPath("release-error.png"), animations: "disabled" });
    await notice.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(notice).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

for (const [language, closeLabel] of [["en", "Close"], ["zh-CN", "关闭"]]) test(`touch users can dismiss a persistent cleanup notice without hovering in ${language}`, async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  try {
    const page = await context.newPage();
    await page.goto(`/browser/fixture.html?case=provider-model-rebuild&lang=${language}&theme=light&oauthReleaseFailure`);
    await page.getByRole("button", { name: "Release inactive sign-in", exact: true }).tap();
    const notice = page.locator('[data-slot="toast"]');
    await expect(notice).toBeInViewport({ ratio: 1 });
    const close = notice.getByRole("button", { name: closeLabel, exact: true });
    await expect(close).toHaveCSS("opacity", "1");
    await close.tap();
    await expect(notice).toHaveCount(0);
  } finally {
    await context.close();
  }
});
