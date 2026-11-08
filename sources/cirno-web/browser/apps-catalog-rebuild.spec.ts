import { expect, test } from "@playwright/test";
for (const width of [390, 1440]) for (const theme of ["light", "dark"]) {
  test(`catalog custom configuration is usable at ${width}px in ${theme}`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/browser/fixture.html?case=apps&manage&lang=en&theme=${theme}`);
    await expect(page.getByRole("button", { name: "Custom", exact: true })).toBeInViewport();
    await page.screenshot({ path: info.outputPath("catalog.png"), animations: "disabled" });
    const search = page.getByRole("searchbox", { name: "Search tools" });
    await search.fill("No matching integration");
    await expect(page.getByText("No tools match your search.")).toBeVisible();
    await search.fill("");
    await page.getByRole("button", { name: "Custom", exact: true }).click();
    await expect(page.getByRole("button", { name: "Save MCP server", exact: true })).toBeDisabled();
    await page.getByRole("textbox", { name: /^Server name/ }).fill("research-library");
    await page.getByRole("button", { name: /Transport$/ }).click();
    await page.getByRole("option", { name: "HTTP", exact: true }).click();
    await page.getByRole("textbox", { name: /^URL/ }).fill("https://library.example/mcp");
    const authentication = page.getByRole("button", { name: /Authentication$/ });
    await authentication.click();
    await page.getByRole("option", { name: "OAuth", exact: true }).click();
    await expect(page.getByText("Save the server, then select Connect to sign in.")).toBeVisible();
    await page.getByRole("button", { name: "Advanced options", exact: true }).click();
    await page.getByRole("textbox", { name: "Call timeout (seconds)", exact: true }).fill("120");
    await page.getByRole("button", { name: "Save MCP server", exact: true }).click();
    await expect(page.getByTestId("mcp-actions")).toContainText('"auth":"oauth"');
    await page.screenshot({ path: info.outputPath("custom.png"), animations: "disabled" });
    await page.getByRole("button", { name: "Import", exact: true }).click();
    const form = page.getByRole("form", { name: "Import mcp.json", exact: true });
    const json = form.getByRole("textbox", { name: "Import mcp.json", exact: true });
    await json.fill('{"mcpServers":{"docs":{"command":"npx"}}}');
    await form.getByRole("button", { name: "Format JSON", exact: true }).click();
    await expect(json).toHaveValue(JSON.stringify({ mcpServers: { docs: { command: "npx" } } }, null, 2));
    await form.getByRole("button", { name: "Import", exact: true }).click();
    await expect(page.getByTestId("mcp-actions")).toContainText('"action":"import"');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}

for (const width of [390, 1440]) {
  test(`CLI catalog exposes installation and management actions at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/browser/fixture.html?case=apps&manage&cli&lang=en&theme=light");
    const installed = page.getByRole("article", { name: "Research CLI", exact: true });
    const available = page.getByRole("article", { name: "Document tools", exact: true });
    await available.getByRole("button", { name: "Install app", exact: true }).click();
    await expect(page.getByTestId("mcp-actions")).toContainText('"action":"install"');
    await page.screenshot({ path: info.outputPath("cli.png"), animations: "disabled" });
    const label = await installed.getByRole("heading", { name: "Research CLI", exact: true }).boundingBox();
    const actions = await installed.getByRole("button", { name: "More actions: Research CLI", exact: true }).boundingBox();
    expect(label!.x + label!.width).toBeLessThanOrEqual(actions!.x);
    await installed.getByRole("button", { name: "More actions: Research CLI", exact: true }).click();
    await page.getByRole("menuitem", { name: "Test app", exact: true }).click();
    await expect(page.getByTestId("mcp-actions")).toContainText('"action":"test"');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
