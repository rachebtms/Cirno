import { expect, test } from "@playwright/test";
import { readPreviewPreferences, seedPreviewPreferences } from "./preference-driver";

for (const width of [390, 1280]) test(`memory cloud expands and returns without another search at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 950 });
  await seedPreviewPreferences(page, { language: "en", themeMode: "dark" });
  await page.goto("/browser/fixture.html?case=memory-graph");
  await page.getByRole("button", { name: "Open Memory", exact: true }).click();
  const cloud = page.locator(".memory-cloud-scene canvas");
  await expect(cloud).toBeVisible();
  const original = (await cloud.boundingBox())!;
  const calls = await page.getByTestId("memory-graph-calls").textContent();
  for (const close of ["escape", "button"]) {
    await page.getByRole("button", { name: "Expand view", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Memory cloud", exact: true });
    await expect(dialog.locator("canvas")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Fit to view", exact: true })).toBeEnabled();
    await dialog.getByRole("button", { name: "Fit to view", exact: true }).click();
    await expect(cloud).toHaveCount(1);
    await expect.poll(async () => (await cloud.boundingBox())!.height).toBeGreaterThan(original.height);
    expect((await dialog.boundingBox())!.width).toBeLessThanOrEqual(width);
    if (close === "escape") {
      await page.screenshot({ path: `/tmp/cirno-memory-expanded-${width}.png` });
      await page.keyboard.press("Escape");
    } else await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(cloud).toBeVisible();
    await expect(page.getByRole("button", { name: "Expand view", exact: true })).toBeFocused();
  }
  await expect(page.getByTestId("memory-graph-calls")).toHaveText(calls!);
  await expect(page.getByRole("button", { name: "Detector calibration 1", exact: true })).toBeVisible();
});

for (const language of ["en", "zh-CN"]) for (const width of [390, 1280]) {
  test(`memory graph search, inspection and singleton in ${language} at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 950 });
    await seedPreviewPreferences(page, { language });
    await page.goto("/browser/fixture.html?case=memory-graph");
    const zh = language === "zh-CN";
    const launcher = page.getByRole("navigation", { name: "Launcher" });
    await launcher.getByRole("button", { name: zh ? "打开记忆" : "Open Memory", exact: true }).click();
    await expect(page.getByText(zh ? "30 条记忆" : "30 memories", { exact: true })).toBeVisible();
    await expect(page.locator(".memory-cloud-scene canvas")).toBeVisible();
    await expect(page.getByText(/3D view could not start|三维视图无法启动/)).toHaveCount(0);
    await expect(page.getByRole("button", { name: zh ? "适应视图" : "Fit to view" })).toBeEnabled();
    const legend = (await page.locator(".memory-cloud-legend").boundingBox())!;
    const help = (await page.locator(".memory-cloud-help").boundingBox())!;
    expect(legend.y + legend.height).toBeLessThanOrEqual(help.y);
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `/tmp/cirno-memory-cloud-${language}-${width}.png`, fullPage: true });
    await page.getByRole("button", { name: zh ? "加载全部" : "Load all", exact: true }).click();
    await expect(page.getByText(zh ? "72 条记忆" : "72 memories", { exact: true })).toBeVisible();
    await expect(page.locator(".memory-record-list > li")).toHaveCount(72);
    await expect(page.getByRole("button", { name: zh ? "加载全部" : "Load all", exact: true })).toHaveCount(0);
    await page.screenshot({ path: `/tmp/cirno-memory-cloud-all-${language}-${width}.png`, fullPage: true });
    await launcher.getByRole("button", { name: zh ? "打开记忆" : "Open Memory", exact: true }).click();
    await expect(page.getByRole("tab", { name: zh ? "记忆" : "Memory", exact: true })).toHaveCount(1);
    const query = page.getByRole("textbox", { name: zh ? "搜索记忆" : "Search memories" });
    await query.fill("Detector");
    await page.getByRole("button", { name: zh ? "搜索记忆" : "Search memories", exact: true }).click();
    await expect(page.getByText(zh ? "12 条记忆" : "12 memories", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Detector calibration 1", exact: true }).click();
    const inspector = page.getByRole("dialog", { name: "Detector calibration 1", exact: true });
    await expect(inspector.getByText("Exact measured temperature: 25.125 °C.")).toBeVisible();
    await page.keyboard.press("Escape");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const calls = JSON.parse((await page.getByTestId("memory-graph-calls").textContent())!);
    expect(calls.filter((call: { action: string }) => call.action === "memory.graph")).toHaveLength(4);
  });
}

for (const width of [390, 1280]) test(`memory display limit persists and loads above 300 at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 950 });
  await seedPreviewPreferences(page, { language: "en" });
  await page.goto("/browser/fixture.html?case=memory-graph&count=360");
  const open = () => page.getByRole("navigation", { name: "Launcher" }).getByRole("button", { name: "Open Memory", exact: true }).click();
  await open();
  const limit = page.getByRole("spinbutton", { name: "Memory limit" });
  await expect(limit).toHaveValue("300");
  await limit.fill("0"); await limit.press("Tab");
  await expect(page.getByText("Enter a positive whole number.", { exact: true })).toBeVisible();
  await limit.fill("360"); await limit.press("Enter");
  await expect.poll(async () => (await readPreviewPreferences(page)).memoryGraphLimit).toBe(360);
  await page.getByRole("button", { name: "Load all", exact: true }).click();
  await expect(page.getByText("360 memories", { exact: true })).toBeVisible();
  await expect(page.locator(".memory-record-list > li")).toHaveCount(360);
  await expect(page.getByRole("button", { name: "Load all", exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator(".memory-library-heading").scrollIntoViewIfNeeded();
  await page.screenshot({ path: `/tmp/cirno-memory-limit-${width}.png` });
  await limit.fill("25"); await limit.press("Enter");
  await expect(page.getByText("25 memories", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Load all", exact: true })).toHaveCount(0);
  await page.reload(); await open();
  await expect(limit).toHaveValue("25");
  await expect(page.getByText("25 memories", { exact: true })).toBeVisible();
});

test("memory view follows pane size across split, mobile and desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await seedPreviewPreferences(page, { language: "en", themeMode: "dark" });
  await page.goto("/browser/fixture.html?case=memory-graph");
  await page.getByRole("navigation", { name: "Launcher" }).getByRole("button", { name: "Open Memory", exact: true }).click();
  await expect(page.locator(".memory-cloud-scene canvas")).toBeVisible();
  await page.getByRole("button", { name: "Split view", exact: true }).click();
  await page.getByRole("button", { name: "Move to other tab group", exact: true }).click();
  await expect(page.locator("[data-split]")).toBeVisible();
  const cloud = page.locator(".memory-cloud"), results = page.locator(".memory-explorer-results");
  await expect.poll(async () => (await results.boundingBox())!.y >= (await cloud.boundingBox())!.y + (await cloud.boundingBox())!.height).toBe(true);
  await page.waitForTimeout(1000);
  await page.screenshot({ path: "/tmp/cirno-memory-cloud-split.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 950 });
  await expect(page.locator("[data-split]")).toHaveCount(0);
  await expect(page.locator(".memory-cloud-scene canvas")).toBeVisible();
  await expect.poll(async () => (await cloud.boundingBox())!.width < 390).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expect(page.locator("[data-split]")).toBeVisible();
  await expect(page.locator(".memory-cloud-scene canvas")).toHaveCount(1);
  await page.getByRole("button", { name: "Close Memory", exact: true }).click();
  await expect(page.locator(".memory-cloud-scene canvas")).toHaveCount(0);
});
