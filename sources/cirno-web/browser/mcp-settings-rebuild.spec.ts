import { expect, test } from "@playwright/test";
for (const width of [390, 1440]) for (const theme of ["light", "dark"]) {
  test(`MCP management preserves drafts through nested forms at ${width}px in ${theme}`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/browser/fixture.html?case=mcp-settings-rebuild&lang=en&theme=${theme}`);
    const manager = page.getByRole("dialog", { name: "Research library", exact: true });
    await manager.getByText("search_papers", { exact: true }).click();
    await expect(manager.getByRole("checkbox", { name: "search_papers" })).not.toBeChecked();
    await manager.getByRole("searchbox", { name: "Search tools" }).fill("write");
    await expect(manager.getByRole("checkbox", { name: "write_note" })).toBeChecked();
    await manager.getByRole("searchbox", { name: "Search tools" }).fill("");
    await expect(manager).toHaveJSProperty("scrollWidth", await manager.evaluate(element => element.clientWidth));
    const status = await manager.getByText("Connected", { exact: true }).boundingBox();
    const close = await manager.getByRole("button", { name: "Close", exact: true }).boundingBox();
    expect(status!.x + status!.width).toBeLessThanOrEqual(close!.x);
    if (width === 390) {
      await page.setViewportSize({ width, height: 600 });
      await expect(manager.getByRole("button", { name: "Save changes", exact: true })).toBeInViewport();
      await expect(manager.getByRole("button", { name: "Close", exact: true })).toBeInViewport();
    }
    await page.screenshot({ path: info.outputPath("tools.png"), animations: "disabled" });
    await page.setViewportSize({ width, height: 900 });
    await manager.getByRole("tab", { name: "Connection", exact: true }).click();
    await manager.getByRole("button", { name: "Configure proxy", exact: true }).click();
    const setup = page.getByRole("dialog", { name: "Shared proxy", exact: true });
    await setup.getByRole("textbox", { name: "Shared proxy", exact: true }).fill("http://localhost:7890");
    await setup.getByRole("button", { name: "Authentication (optional)" }).click();
    await setup.getByRole("textbox", { name: "Username", exact: true }).fill("researcher");
    await setup.getByLabel("Password", { exact: true }).fill("secret");
    await page.screenshot({ path: info.outputPath("proxy.png"), animations: "disabled" });
    await setup.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(manager).toBeVisible();
    await manager.getByRole("button", { name: "Edit MCP configuration", exact: true }).click();
    const editor = page.getByRole("dialog", { name: "Edit MCP configuration", exact: true });
    const input = editor.getByRole("textbox", { name: "Edit MCP configuration" });
    await expect(input).toHaveValue(/toolTimeout/);
    await expect(input).toBeFocused();
    await input.fill('{"url":"https://draft.example/mcp"}');
    await editor.getByRole("button", { name: "Save", exact: true }).click();
    await expect(editor.getByRole("alert")).toContainText("Configuration save failed");
    await expect(input).toHaveValue('{"url":"https://draft.example/mcp"}');
    await page.screenshot({ path: info.outputPath("config-error.png"), animations: "disabled" });
    await editor.getByRole("button", { name: "Save", exact: true }).click();
    await expect(editor).not.toBeVisible();
    await manager.getByRole("tab", { name: "Tools", exact: true }).click();
    await expect(manager.getByRole("checkbox", { name: "search_papers" })).not.toBeChecked();
    await manager.getByRole("button", { name: "Save changes", exact: true }).click();
    await expect(manager.getByRole("button", { name: "Save changes", exact: true })).not.toBeVisible();
    expect(errors).toEqual([]);
  });
}
