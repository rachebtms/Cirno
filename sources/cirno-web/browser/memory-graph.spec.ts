import { expect, test } from "@playwright/test";
import { seedPreviewPreferences } from "./preference-driver";

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
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `/tmp/cirno-memory-cloud-${language}-${width}.png`, fullPage: true });
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
    expect(calls.filter((call: { action: string }) => call.action === "memory.graph")).toHaveLength(2);
  });
}

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
