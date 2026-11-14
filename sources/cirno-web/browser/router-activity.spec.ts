import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  test(`Router groups heartbeat work at ${width}px`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/browser/fixture.html?case=router-activity&lang=en&theme=dark");
    const thread = page.getByRole("region", { name: "Router conversation" });
    await expect(thread.getByRole("button", { name: /^Worked/ })).toHaveCount(1);
    const header = thread.getByRole("button", { name: "Worked for 12s", exact: true });
    await expect(header).toHaveAttribute("aria-expanded", "false");
    await header.click();
    await expect(thread.getByRole("button", { name: "Heartbeat", exact: true })).toHaveCount(2);
    await expect(thread.getByText("First inspection complete.", { exact: true })).toBeVisible();
    await expect(thread.getByText("Second inspection complete.", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Start heartbeat", exact: true }).click();
    await expect(thread.getByRole("button", { name: /^Working for/ })).toHaveCount(1);
    await expect(thread.getByRole("button", { name: /^Worked/ })).toHaveCount(0);
    await expect(thread.getByRole("button", { name: "Heartbeat", exact: true })).toHaveCount(3);
    await page.getByRole("button", { name: "Finish heartbeat", exact: true }).click();
    await expect(thread.getByRole("button", { name: /^Worked for 15s/ })).toHaveCount(1);
    await thread.getByRole("button", { name: /^Worked for 15s/ }).click();
    await expect(thread.getByRole("button", { name: /^Worked/ })).toHaveAttribute("aria-expanded", "false");
    await expect(thread.getByRole("button", { name: "Heartbeat", exact: true })).not.toBeVisible();
    await page.screenshot({ path: info.outputPath("router-activity-collapsed.png"), animations: "disabled" });
    await thread.getByRole("button", { name: /^Worked for 15s/ }).click();
    await thread.getByRole("button", { name: "Heartbeat", exact: true }).nth(2).click();
    await expect(thread.getByText("Inspect authorized tasks (current).", { exact: true })).toBeVisible();
    await page.screenshot({ path: info.outputPath("router-activity-expanded.png"), animations: "disabled" });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}
