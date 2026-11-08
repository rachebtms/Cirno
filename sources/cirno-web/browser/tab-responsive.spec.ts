import { expect, test } from "@playwright/test";

for (const theme of ["light", "dark"]) test(`tab width owns layout across splits, moves and phone restoration (${theme})`, async ({ page }) => {
  await page.setViewportSize({ width: 2000, height: 1000 });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(`/browser/fixture.html?case=workspace&paneSettings&lang=en&theme=${theme}`);
  const launcher = page.getByRole("navigation", { name: "Launcher", exact: true });
  await launcher.getByRole("button", { name: "Open Settings", exact: true }).click();
  await expect(page.locator(".settings-desktop-navigation")).toBeVisible();
  await page.getByRole("button", { name: "Split view", exact: true }).click();
  await launcher.getByRole("button", { name: "Open New conversation", exact: true }).click();
  const divider = page.getByRole("separator", { name: "Resize split view" });
  await divider.focus(); await divider.press("Home");
  const pane = page.getByRole("tabpanel", { name: "Settings", exact: true });
  await expect(pane.locator(".settings-mobile-navigation")).toBeVisible();
  await expect(pane.locator(".settings-desktop-navigation")).toHaveCount(0);
  // The source breakdown must stay in one column, instead of spelling labels vertically.
  const breakdown = pane.locator('dl[aria-label="Usage by source"]');
  expect(await breakdown.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(" ").length)).toBe(1);
  expect(await pane.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await page.screenshot({ path: `/tmp/cirno-review87-split-${theme}.png`, fullPage: true });
  await pane.getByRole("button", { name: /^Settings:/ }).click();
  const chooser = page.getByRole("dialog", { name: "Settings", exact: true });
  await chooser.getByRole("searchbox").fill("Context compaction");
  await chooser.getByRole("button", { name: "Context compaction", exact: true }).click();
  const field = pane.getByRole("spinbutton", { name: "Active compaction trigger (%)" });
  await field.fill("73");
  // Moving the same mounted tab to the wide group must switch its layout immediately.
  await page.locator(".workbench-group-bar").nth(0).getByRole("button", { name: "Move to other tab group" }).click();
  await expect(pane.locator(".settings-desktop-navigation")).toBeVisible();
  await expect(field).toHaveValue("73");
  await divider.focus(); await divider.press("End");
  await expect(pane.locator(".settings-mobile-navigation")).toBeVisible();
  await divider.press("Home");
  await expect(pane.locator(".settings-desktop-navigation")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(pane.locator(".settings-mobile-navigation")).toBeVisible();
  await expect(field).toHaveValue("73");
  await page.setViewportSize({ width: 2000, height: 1000 });
  await expect(pane.locator(".settings-desktop-navigation")).toBeVisible();
  await expect(field).toHaveValue("73");
  expect(errors).toEqual([]);
});

test("Trace uses its own width beside a simultaneously wide Settings tab", async ({ page }) => {
  await page.setViewportSize({ width: 2000, height: 1000 });
  await page.goto("/browser/fixture.html?case=workspace&paneSettings&lang=en");
  const launcher = page.getByRole("navigation", { name: "Launcher", exact: true });
  await launcher.getByRole("button", { name: "Open Settings", exact: true }).click();
  await page.getByRole("button", { name: "Split view", exact: true }).click();
  await launcher.getByRole("button", { name: "Open Trace", exact: true }).click();
  const divider = page.getByRole("separator", { name: "Resize split view" });
  await divider.focus(); await divider.press("End");
  const trace = page.locator(".trace-console");
  await trace.locator('[data-event-kind="request"]').first().click();
  await expect(page.locator(".settings-desktop-navigation")).toBeVisible();
  expect(await trace.locator(".trace-toolbar").evaluate(el => getComputedStyle(el).gridTemplateColumns.split(" ").length)).toBe(2);
  expect(await trace.locator(".trace-content").evaluate(el => getComputedStyle(el).flexDirection)).toBe("column");
  expect(await trace.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await divider.focus(); await divider.press("Home");
  await expect(page.locator(".settings-mobile-navigation")).toBeVisible();
  expect(await trace.locator(".trace-toolbar").evaluate(el => getComputedStyle(el).gridTemplateColumns.split(" ").length)).toBe(4);
  expect(await trace.locator(".trace-content").evaluate(el => getComputedStyle(el).flexDirection)).toBe("row");
});
