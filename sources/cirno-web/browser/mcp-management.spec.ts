import { expect, test } from "@playwright/test";

for (const width of [390, 1100]) {
  test(`MCP body opens management without connecting at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 });
    await page.goto("/browser/fixture.html?case=apps&manage");
    const actions = page.getByTestId("mcp-actions");
    const body = page.getByRole("button", { name: "Design MCP", exact: true });
    const dialog = page.getByRole("dialog", { name: "Design MCP", exact: true });
    await body.click();
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    await expect(actions).toHaveText("[]");
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await body.focus();
    await page.keyboard.press(width === 390 ? "Enter" : "Space");
    await expect(dialog).toBeVisible();
    await expect(actions).toHaveText("[]");
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await page.getByRole("button", { name: "Connect Design MCP" }).click();
    await expect(dialog.getByRole("tab", { name: "Connection", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(actions).toHaveText("[]");
    await dialog.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(actions).toHaveText(JSON.stringify([{
      action: "oauth", name: "design", reset: false, values: { use_proxy: "false" },
    }]));
  });
}

for (const width of [390, 1440]) {
  test(`custom MCP editing and JSON import remain usable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 });
    await page.goto("/browser/fixture.html?case=apps&custom-edit");
    await expect(page.getByRole("button", { name: "Custom", exact: true })).toBeInViewport();
    await expect(page.getByRole("button", { name: "Import", exact: true })).toBeInViewport();
    await page.screenshot({ animations: "disabled", path: `/tmp/cirno-mcp-top-${width}.png` });
    await page.getByRole("button", { name: "Manage Docs MCP" }).click();
    await page.getByRole("tab", { name: "Connection", exact: true }).click();
    const connection = page.getByRole("dialog", { name: "Docs MCP", exact: true });
    await expect(connection.getByRole("button", { name: "Edit MCP configuration" })).toBeVisible();
    await page.screenshot({ animations: "disabled", path: `/tmp/cirno-mcp-connection-${width}.png` });
    await connection.getByRole("button", { name: "Edit MCP configuration" }).click();
    const dialog = page.getByRole("dialog", { name: "Edit MCP configuration", exact: true });
    const editor = dialog.getByRole("textbox");
    await expect(editor).toContainText('  "command": "npx"');
    await page.screenshot({ animations: "disabled", path: `/tmp/cirno-mcp-editor-${width}.png` });
    const bounds = await dialog.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    expect(bounds!.y).toBeGreaterThanOrEqual(0);
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(850);
    const original = JSON.parse(await editor.inputValue());
    await editor.fill(JSON.stringify({ ...original, command: "node" }));
    await dialog.getByRole("button", { name: "Save", exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await expect(connection.getByText("node -y docs-mcp", { exact: true })).toBeVisible();
    await connection.getByRole("button", { name: "Edit MCP configuration" }).click();
    await expect(editor).toContainText('  "command": "node"');
    expect(JSON.parse(await editor.inputValue()).env).toEqual(original.env);
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await connection.getByRole("button", { name: "Close", exact: true }).click();
    await page.getByRole("button", { name: "Import", exact: true }).click();
    await page.getByRole("button", { name: "Import mcp.json", exact: true }).click();
    const importer = page.getByRole("dialog", { name: "Import mcp.json", exact: true });
    expect(await importer.getByRole("textbox").getAttribute("placeholder")).toContain('\n  "mcpServers":');
    await importer.getByRole("textbox").fill('{"mcpServers":{"docs":{"command":"npx"}}}');
    await importer.getByRole("button", { name: "Format JSON", exact: true }).click();
    await expect(importer.getByRole("textbox")).toContainText('    "docs": {');
    await page.screenshot({ animations: "disabled", path: `/tmp/cirno-mcp-import-${width}.png` });
  });
}

for (const width of [390, 1440]) {
  test(`custom MCP editor is localized in dark mode at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 });
    await page.goto("/browser/fixture.html?case=apps&custom-edit&lang=zh-CN");
    await page.evaluate(() => document.documentElement.classList.add("dark"));
    await page.getByRole("button", { name: "Docs MCP", exact: true }).click();
    await page.getByRole("tab", { name: "连接", exact: true }).click();
    await page.getByRole("button", { name: "编辑 MCP 配置", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "编辑 MCP 配置", exact: true });
    await expect(dialog.getByRole("textbox")).toHaveValue(/\n {2}"command": "npx"/);
    await expect(dialog.getByRole("button", { name: "格式化 JSON" })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "保存", exact: true })).toBeVisible();
    await expect(dialog.getByRole("textbox")).toBeFocused();
    await page.screenshot({ animations: "disabled", path: `/tmp/cirno-mcp-dark-zh-${width}.png` });
  });
}
