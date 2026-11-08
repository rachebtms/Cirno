import { expect, test } from "@playwright/test";
for (const width of [390, 1440]) for (const theme of ["light", "dark"]) {
  test(`directory, editor and live preview at ${width}px in ${theme}`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/browser/fixture.html?case=workspace&lang=en&theme=${theme}`);
    await page.getByRole("button", { name: "Open Files", exact: true }).click();
    await page.getByRole("button", { name: "notes.md", exact: true }).click();
    const editor = page.getByRole("textbox", { name: "File contents" });
    await expect(editor).toBeVisible();
    await editor.fill("# Updated observations\n\nA preview shared across tabs.");
    await page.getByRole("button", { name: "Open preview tab", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Updated observations" })).toBeVisible();
    await page.getByRole("tab", { name: "notes.md", exact: true }).click();
    await expect(editor).toHaveValue("# Updated observations\n\nA preview shared across tabs.");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
    await page.screenshot({ path: test.info().outputPath("files-editor.png") });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}
