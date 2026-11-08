import { expect, test, type Page } from "@playwright/test";

async function projectMenu(page: Page, name = "Research") {
  await page.getByRole("button", { name: `Project actions for ${name}`, exact: true }).click();
}
for (const width of [390, 1440]) {
  test(`project editors retain failures and update the canonical project at ${width}px`, async ({ page }, info) => {
    const longName = `Research-${"x".repeat(110)}`;
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/browser/fixture.html?case=conversations&lang=en&theme=${width === 390 ? "light" : "dark"}&saveFailure`);
    await expect(page.getByRole("heading", { name: "Research", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "New project", exact: true }).click();
    const editor = page.getByRole("dialog", { name: "New project", exact: true });
    await editor.getByRole("textbox", { name: /^Project name/ }).fill(longName);
    await editor.getByRole("textbox", { name: "Working directory (optional)", exact: true }).fill("/same");
    await editor.getByRole("button", { name: "Create", exact: true }).click();
    await expect(editor.getByRole("alert")).toContainText("Project save unavailable");
    await expect(editor.getByRole("textbox", { name: /^Project name/ })).toHaveValue(longName);
    await page.screenshot({ path: info.outputPath("project-failed-save.png"), animations: "disabled" });
    await editor.getByRole("button", { name: "Create", exact: true }).click();
    await expect(editor).toHaveCount(0);
    const heading = page.getByRole("heading", { name: longName, exact: true });
    await expect(heading).toBeVisible();
    expect(await heading.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await projectMenu(page, longName);
    await page.getByRole("menuitem", { name: "Rename", exact: true }).click();
    const rename = page.getByRole("dialog");
    expect(await rename.getByRole("heading").evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await expect(rename.getByRole("textbox", { name: "Working directory (optional)", exact: true })).toHaveValue("/same");
    await rename.getByRole("textbox", { name: /^Project name/ }).fill("Corrected research");
    await rename.getByRole("button", { name: "Save", exact: true }).click();
    await expect(rename).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Corrected research", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`failed membership and deletion remain retryable at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/browser/fixture.html?case=conversations&lang=en&theme=dark&assignFailure&deleteFailure");
    const project = page.getByRole("region", { name: "Research", exact: true });
    await page.getByRole("button", { name: "Conversation actions for Review paper", exact: true }).click();
    const projects = page.getByRole("menuitem", { name: "Projects", exact: true });
    await projects.focus(); await page.keyboard.press("ArrowRight");
    await page.getByRole("menuitemradio", { name: "Unfiled conversations", exact: true }).click();
    const error = page.getByRole("alert");
    await expect(error).toContainText("Project assign unavailable");
    await expect(project.getByRole("button", { name: "Review paper", exact: true })).toBeVisible();
    await error.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(error).toHaveCount(0);
    await expect(project.getByRole("button", { name: "Review paper", exact: true })).toHaveCount(0);
    await projectMenu(page);
    await page.getByRole("menuitem", { name: "Delete", exact: true }).click();
    const confirm = page.getByRole("alertdialog");
    await confirm.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(confirm.getByRole("alert")).toContainText("Project delete unavailable");
    await page.screenshot({ path: info.outputPath("project-failed-delete.png"), animations: "disabled" });
    await page.keyboard.press("F8"); await expect(confirm).toHaveCount(0);
    await page.keyboard.press("F8");
    await expect(confirm.getByRole("alert")).toContainText("Project delete unavailable");
    await confirm.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(confirm).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Research", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Review paper", exact: true })).toBeVisible();
  });
}

test("a large catalog searches records outside its mounted pages", async ({ page }) => {
  await page.goto("/browser/fixture.html?case=conversations&lang=en&theme=dark&many");
  await expect(page.getByRole("button", { name: "Show more", exact: true })).toBeVisible();
  expect(await page.locator("[data-chat-row]").count()).toBeLessThan(40);
  await page.getByRole("searchbox", { name: "Search conversations and projects", exact: true }).fill("Research record 1499");
  await expect(page.getByRole("button", { name: "Research record 1499", exact: true })).toBeVisible();
  await expect(page.locator("[data-chat-row]")).toHaveCount(1);
});
