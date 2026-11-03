import { expect, test } from "@playwright/test";

for (const locale of ["en", "zh-CN"]) for (const width of [390, 1280]) {
  test(`long-work settings in ${locale} at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript((language) => localStorage.setItem("cirno.locale", language), locale);
    const chinese = locale === "zh-CN";
    await page.goto("/browser/fixture.html?case=idle-compaction");
    await expect(page.getByRole("spinbutton", { name: chinese ? "压缩输出预算（Token）" : "Checkpoint output budget (tokens)" })).toHaveValue("8192");
    await expect(page.getByRole("combobox", { name: chinese ? "压缩思考强度" : "Checkpoint reasoning effort" })).toHaveText(chinese ? "低" : "Low");
    await page.getByTestId("settings-section-transition").evaluate(async (el) => { await Promise.all(el.getAnimations({ subtree: true }).map((animation) => animation.finished)); });
    await page.screenshot({ path: test.info().outputPath(`context-${locale}-${width}.png`), fullPage: true });
    await page.goto("/browser/fixture.html?case=idle-compaction&section=memory-search");
    const key = page.getByLabel(chinese ? "API 密钥" : "API key", { exact: true });
    await expect(key).toHaveAttribute("type", "password");
    await expect(key).toHaveValue("••••••••");
    await expect(page.getByRole("textbox", { name: chinese ? "嵌入模型" : "Embedding model", exact: true })).toHaveValue("research-embedding");
    await expect(page.getByRole("textbox", { name: chinese ? "ONNX 模型路径" : "ONNX model path" })).toHaveCount(0);
    if (width === 390 && chinese) await page.evaluate(() => document.documentElement.classList.add("dark"));
    await page.getByTestId("settings-section-transition").evaluate(async (el) => { await Promise.all(el.getAnimations({ subtree: true }).map((animation) => animation.finished)); });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({ path: test.info().outputPath(`embedding-${locale}-${width}.png`), fullPage: true });
    await page.goto("/browser/fixture.html?case=idle-compaction&section=models");
    await page.getByTestId("model-call-order-row-primary").getByRole("button").first().click();
    const replay = page.getByRole("combobox", { name: chinese ? "历史思考回传" : "Reasoning history" });
    await expect(replay).toBeVisible();
    await replay.click();
    await expect(page.getByRole("option", { name: chinese ? "保留" : "Preserve", exact: true })).toBeVisible();
    await page.screenshot({ path: test.info().outputPath(`model-${locale}-${width}.png`), fullPage: true });
  });
}
