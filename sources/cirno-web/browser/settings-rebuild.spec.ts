import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) for (const theme of ["light", "dark"]) {
  test(`settings navigation and inline editing at ${width}px in ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/v0/auth/status", route => route.fulfill({ json: {
      enabled: true, authenticated: true, registration_required: false, username: "research-owner",
    } }));
    await page.goto(`/browser/fixture.html?case=settings-rebuild&lang=en&theme=${theme}`);
    // Capture transient actions too: a final-state assertion alone misses the flash.
    await page.evaluate(() => {
      document.documentElement.dataset.saveFlashed = "false";
      new MutationObserver(records => {
        if (records.some(record => [...record.addedNodes].some(node => node instanceof Element
          && [node, ...node.querySelectorAll("button")].some(element => element.matches("button")
            && element.textContent?.trim() === "Save changes")))) {
          document.documentElement.dataset.saveFlashed = "true";
        }
      }).observe(document.body, { childList: true, subtree: true });
    });
    const trigger = page.getByRole("spinbutton", { name: "Active consolidation trigger (%)" });
    await trigger.fill("73");
    await expect(page.getByLabel("Saved settings")).toHaveText('{"agents.defaults.active_compact_percent":73}');
    const navigate = async (label: string) => {
      if (width < 1024) {
        await page.getByRole("button", { name: /^Settings:/ }).click();
        const chooser = page.getByRole("dialog", { name: "Settings", exact: true });
        await chooser.getByRole("searchbox").fill(label);
        await chooser.getByRole("button", { name: label, exact: true }).click();
        await expect(chooser).not.toBeVisible();
      } else await page.getByRole("button", { name: label, exact: true }).click();
    };
    const retries = page.getByRole("spinbutton", { name: "Consolidation generation retries" });
    await retries.fill("0");
    await retries.press("Enter");
    await expect(page.getByLabel("Saved settings")).toHaveText('{"agents.defaults.consolidation.max_retries":0}');
    await page.getByText("Consolidate idle conversations", { exact: true }).click();
    await expect(page.getByLabel("Saved settings")).toHaveText('{"agents.defaults.idle_compact_after_minutes":0}');
    await navigate("Goals & execution");
    const workspace = page.getByRole("textbox", { name: "Default workspace" });
    await workspace.fill("/research");
    await workspace.press("Enter");
    await expect(page.getByLabel("Saved settings")).toHaveText('{"agents.defaults.workspace":"/research"}');
    await navigate("Network & retries");
    const proxy = page.getByRole("textbox", { name: "Shared proxy", exact: true });
    await proxy.fill("http://localhost:7890");
    await proxy.blur();
    await expect(page.getByLabel("Saved settings")).toHaveText('{"network.proxy":"http://localhost:7890"}');
    await page.screenshot({ path: test.info().outputPath("automatic-save.png") });
    await navigate("Shell execution");
    await expect(page.getByRole("textbox", { name: "Environment variables" })).toBeVisible();
    const duration = page.getByRole("spinbutton", { name: "Custom runtime (seconds)" });
    await duration.fill("900");
    await expect(duration).toBeFocused();
    await duration.press("End"); await duration.press("0");
    await expect(duration).toHaveValue("9000");
    await navigate("Account");
    await expect(page.getByText("research-owner", { exact: true })).toBeVisible();
    await expect(page.getByLabel("New password", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.locator("html")).toHaveAttribute("data-save-flashed", "false");
    expect(errors).toEqual([]);
  });
}
