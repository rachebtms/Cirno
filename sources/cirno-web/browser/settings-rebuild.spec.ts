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
    const trigger = page.getByRole("spinbutton", { name: "Active compaction trigger (%)" });
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
    expect(errors).toEqual([]);
  });
}
