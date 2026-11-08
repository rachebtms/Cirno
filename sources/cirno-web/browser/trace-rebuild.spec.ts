import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) for (const theme of ["light", "dark"]) test(`recording filters, details and controls work at ${width}px in ${theme}`, async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.setViewportSize({ width, height: 900 });
  await page.goto(`/browser/fixture.html?case=trace-rebuild&lang=en&theme=${theme}`);
  const table = page.getByRole("grid", { name: "Recorded events", exact: true });
  await expect(table.getByRole("row")).toHaveCount(26);
  const request = table.locator('[data-event-kind="request"]').first();
  expect((await request.boundingBox())!.height).toBeLessThan(36);
  await request.click();
  const inspector = page.getByRole("region", { name: "Event inspector", exact: true });
  await expect(inspector.getByRole("tab", { name: "Messages", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(inspector.getByRole("tabpanel")).toContainText("Shared model instructions");
  await inspector.getByRole("tab", { name: "Tools", exact: true }).click();
  await expect(inspector.getByRole("tabpanel")).toContainText("nodes.execute");
  await page.getByRole("button", { name: /Type$/ }).click();
  await page.getByRole("option", { name: "Tool call", exact: true }).click();
  await page.getByRole("button", { name: /Source conversation$/ }).click();
  await page.getByRole("option", { name: "@worker", exact: true }).click();
  await expect(table.locator('[data-event-kind="tool_activity"]')).toHaveCount(3);
  await table.locator('[data-event-kind="tool_activity"]').first().click();
  await expect(inspector.getByRole("tab", { name: "Raw", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(inspector.getByRole("tabpanel")).toContainText('"command": "nvidia-smi"');
  await page.getByRole("searchbox", { name: "Filter this page", exact: true }).fill("nvidia");
  await page.getByRole("button", { name: "Pause recording", exact: true }).click();
  await expect(page.getByRole("button", { name: "Start recording", exact: true })).toBeEnabled();
  await page.screenshot({ path: info.outputPath("trace.png"), animations: "disabled" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "Start recording", exact: true }).click();
  await page.getByRole("button", { name: "Clear recording", exact: true }).click();
  await expect(inspector).not.toBeVisible();
  await expect(page.getByText("Recording new events. Earlier conversation history is not captured.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close recording tab", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Recording closed", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});


test("an empty recording stays stable across background polls", async ({ page }) => {
  await page.goto("/browser/fixture.html?case=trace-rebuild&emptyPolling&lang=en&theme=dark");
  const empty = page.getByText("Recording new events. Earlier conversation history is not captured.", { exact: true });
  await expect(empty).toBeVisible();
  await page.evaluate(() => {
    const status = document.querySelector(".trace-empty")!;
    status.setAttribute("data-stable-status", "true");
    const values: string[] = [];
    Object.assign(window, { traceStatusChanges: values });
    new MutationObserver(() => values.push(status.textContent ?? "")).observe(status, { childList: true, characterData: true, subtree: true });
  });
  await expect.poll(async () => {
    const raw = await page.getByLabel("Trace actions", { exact: true }).textContent();
    return JSON.parse(raw ?? "[]").filter((item: { action: string }) => item.action === "trace.events").length;
  }, { timeout: 10000 }).toBeGreaterThanOrEqual(3);
  await expect(page.locator('[data-stable-status="true"]')).toHaveText("Recording new events. Earlier conversation history is not captured.");
  expect(await page.evaluate(() => Reflect.get(window, "traceStatusChanges"))).toEqual([]);
  await expect(page.getByRole("button", { name: "Pause recording", exact: true })).toBeEnabled();
});


test("downloads a recording and copies the selected inspector section", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/browser/fixture.html?case=trace-rebuild&lang=en&theme=dark");
  await expect(page.getByRole("button", { name: "Download recording ZIP", exact: true })).toBeEnabled();
  const transfer = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download recording ZIP", exact: true }).click();
  expect((await transfer).suggestedFilename()).toBe("cirno-trace-fixture-recording.zip");
  await page.getByRole("row").filter({ hasText: "Model request" }).first().click();
  await expect(page.getByRole("button", { name: "Copy displayed details", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Copy displayed details", exact: true }).click();
  expect(JSON.parse(await page.evaluate(() => navigator.clipboard.readText()))[0].role).toBe("system");
  await page.getByRole("tab", { name: "Tools", exact: true }).click();
  await page.getByRole("button", { name: "Copy displayed details", exact: true }).click();
  expect(JSON.parse(await page.evaluate(() => navigator.clipboard.readText()))).toEqual([{ name: "nodes.execute" }]);
});
