import { expect, test, type Page } from "@playwright/test";

const key = "cirno.composer-draft.v1.websocket:draft-a";
async function seed(page: Page) {
  await page.addInitScript(key => {
    if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify({
      text: "Review @other", quotedContext: "Saved evidence", sessionMentions: [{ name: "other", session_key: "websocket:other", title: "Other research" }],
      attachments: [{ path: "/workspace/paper.txt", name: "paper.txt", kind: "file", size: 10, mime: "text/plain", url: "" }],
    }));
  }, key);
}
for (const width of [390, 1440]) test.describe(`Draft persistence at ${width}px`, () => {
  test.use({ viewport: { width, height: 960 }, hasTouch: width === 390, isMobile: width === 390 });
  test("retains a failed restore until explicit Retry restores all of its context", async ({ page }) => {
    await seed(page);
    await page.goto("/browser/fixture.html?case=draft-persistence&failure=read&lang=en");
    await expect(page.getByRole("alert")).toContainText("Could not restore this browser’s draft");
    await expect(page.getByRole("textbox", { name: "Message input", exact: true })).toHaveValue("");
    await page.getByRole("button", { name: "Allow draft storage", exact: true }).click();
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "Message input", exact: true })).toHaveValue("Review @other");
    await expect(page.getByText("Saved evidence", { exact: true })).toBeVisible();
    await expect(page.getByTestId("composer-chip")).toContainText("paper.txt");
    await expect(page.getByRole("alert")).toHaveCount(0);
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    await expect(page.getByLabel("Submitted messages")).toContainText('"quotedContext":"Saved evidence"');
    await expect(page.getByLabel("Submitted messages")).toContainText('"path":"/workspace/paper.txt"');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
  test("keeps unsaved edits when changing conversations and makes Retry durable", async ({ page }) => {
    await page.goto("/browser/fixture.html?case=draft-persistence&failure=save&lang=en");
    const input = page.getByRole("textbox", { name: "Message input", exact: true });
    await input.fill("Latest research instructions");
    await expect(page.getByRole("alert")).toContainText("Keep this page open and retry");
    await page.getByRole("button", { name: "Switch conversation", exact: true }).click();
    await input.fill("Independent draft");
    await page.getByRole("button", { name: "Switch conversation", exact: true }).click();
    await expect(input).toHaveValue("Latest research instructions");
    await page.screenshot({ path: `/tmp/cirno-review81-draft-${width}.png`, fullPage: true });
    await page.getByRole("button", { name: "Allow draft storage", exact: true }).click();
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await page.reload();
    await expect(input).toHaveValue("Latest research instructions");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
  test("never clears a newer draft when a previous conversation send is accepted late", async ({ page }) => {
    await page.goto("/browser/fixture.html?case=draft-persistence&delayed&lang=en");
    const input = page.getByRole("textbox", { name: "Message input", exact: true });
    await input.fill("Send this revision");
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    await page.getByRole("button", { name: "Switch conversation", exact: true }).click();
    await page.getByRole("button", { name: "Switch conversation", exact: true }).click();
    await input.fill("Keep the newer revision");
    await page.getByRole("button", { name: "Accept pending send", exact: true }).click();
    await expect(page.getByLabel("Submitted messages")).toContainText('"text":"Send this revision"');
    await expect(input).toHaveValue("Keep the newer revision");
    await page.reload();
    await expect(input).toHaveValue("Keep the newer revision");
  });
});
