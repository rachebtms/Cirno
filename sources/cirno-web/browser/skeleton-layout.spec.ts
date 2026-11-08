import { expect, test } from "@playwright/test";

// Exercise pending-data transitions; exact placeholder pixels are not a contract.
for (const width of [390, 1440]) test.describe(`Pending data at ${width}px`, () => {
  test.use({ viewport: { width, height: 900 }, reducedMotion: "reduce", hasTouch: width === 390 });

  test("a typed model ID survives a delayed catalog and remains selectable", async ({ page }) => {
    let release = () => {};
    const pending = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/v0/settings/provider-models?**", async route => {
      await pending;
      await route.fulfill({ json: {
        provider: "anthropic", label: "Anthropic", status: "available", source: "remote",
        catalog_kind: "official", models: [{ id: "project-model", label: "Project model" }], model_count: 1,
      } });
    });
    try {
      await page.goto("/browser/fixture.html?case=skeleton&surface=models&lang=en");
      const input = page.getByRole("combobox");
      await input.fill("project");
      await expect(page.getByRole("status")).toHaveAttribute("aria-busy", "true");
      await expect(input).toHaveValue("project");
      release();
      await page.getByRole("option", { name: /Project model/ }).click();
      await expect(input).toHaveValue("project-model");
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    } finally { release(); }
  });

  test("folder loading announces progress without selectable placeholder entries", async ({ page }) => {
    let release = () => {};
    const pending = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/v0/workspaces/directories?**", async route => {
      await pending;
      const directory = new URL(route.request().url()).searchParams.get("path")!;
      await route.fulfill({ json: {
        path: directory, parent: "/srv", host: "dev-server", platform: "Linux", truncated: false,
        entries: [{ name: "project-one", path: `${directory}/project-one` }],
      } });
    });
    try {
      await page.goto("/browser/fixture.html?case=skeleton&surface=workspace&lang=en");
      const trigger = page.getByRole("button", { name: "Switch directory", exact: true });
      await trigger.click();
      await expect(page.getByRole("status", { name: "Loading folders…", exact: true })).toBeVisible();
      await expect(page.getByRole("option")).toHaveCount(0);
      release();
      await expect(page.getByRole("option", { name: /project-one/ }).first()).toBeVisible();
      await expect(page.getByRole("status", { name: "Loading folders…", exact: true })).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
      await page.keyboard.press("Escape");
      await expect(trigger).toBeFocused();
    } finally { release(); }
  });
});
