import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) test.describe(`Waiting-message storage at ${width}px`, () => {
  test.use({ viewport: { width, height: 960 }, hasTouch: width === 390, isMobile: width === 390 });
  test("retains attachments and a visible retry across a topic switch when saving fails", async ({ page }) => {
    await page.addInitScript(() => {
      const key = "cirno.webui.composerQueuedGuidance.v1:queued-fixture";
      if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify([{
        id: "saved-evidence", text: "Use this evidence after the current task", autoPaused: true,
        images: [{ name: "experiment-results.txt", kind: "file", dataUrl: "data:text/plain;base64,dmVyaWZpZWQ=" }],
      }]));
    });
    await page.goto("/browser/fixture.html?case=queued-guidance&storageFailure&sendFailure&lang=en");
    const waiting = page.getByRole("group", { name: "Waiting to send", exact: true });
    await expect(waiting).toContainText("experiment-results.txt");
    await page.getByRole("button", { name: "Send now", exact: true }).click();
    const storageError = page.getByRole("alert").filter({ hasText: "Keep this page open and retry" });
    await expect(storageError).toContainText("Queue storage quota exceeded");
    await page.getByRole("button", { name: "Switch topic", exact: true }).click();
    await page.getByRole("button", { name: "Switch topic", exact: true }).click();
    await expect(waiting).toContainText("Use this evidence after the current task");
    await expect(waiting).toContainText("experiment-results.txt");
    await expect(storageError).toBeVisible();
    const surface = (await page.locator(".composer-surface").boundingBox())!;
    for (const alert of await page.getByRole("alert").all()) {
      const bounds = (await alert.boundingBox())!;
      expect(bounds.x).toBeGreaterThanOrEqual(surface.x + 8);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(surface.x + surface.width - 8);
    }
    await page.screenshot({ path: `/tmp/cirno-review80-queue-error-${width}.png`, fullPage: true });
    await page.getByRole("button", { name: "Allow queue storage", exact: true }).click();
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(storageError).toHaveCount(0);
    await expect(page.getByRole("alert")).toHaveText("Fixture upload unavailable");
    await page.reload();
    await expect(waiting).toContainText("experiment-results.txt");
    await expect(page.getByLabel("Submitted messages")).toHaveText("[]");
    await page.getByRole("button", { name: "Allow queue storage", exact: true }).click();
    await page.getByRole("button", { name: "Send now", exact: true }).click();
    await expect(page.getByRole("alert")).toHaveText("Fixture upload unavailable");
    await expect(waiting).toContainText("experiment-results.txt");
    await expect(page.getByLabel("Submitted messages")).toHaveText("[]");
    await page.getByRole("button", { name: "Send now", exact: true }).click();
    await expect(waiting).toHaveCount(0);
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(page.getByLabel("Submitted messages")).toContainText('"name":"experiment-results.txt"');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `/tmp/cirno-review80-queue-sent-${width}.png`, fullPage: true });
  });
});
