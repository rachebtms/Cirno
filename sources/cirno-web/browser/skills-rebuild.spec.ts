import { expect, test } from "@playwright/test";
for (const width of [390, 1440])
  for (const theme of ["light", "dark"]) {
    test(`Skills detail and deletion remain reviewable at ${width}px in ${theme}`, async ({ page }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/browser/fixture.html?case=skills-rebuild&lang=en&theme=${theme}`);
      await page.getByRole("radio", { name: "Enabled 1", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "Open details for weather", exact: true }),
      ).not.toBeVisible();
      await page.getByRole("radio", { name: "All 2", exact: true }).click();
      await page.getByRole("button", { name: "Open details for research", exact: true }).click();
      const dialog = page.getByRole("dialog", { name: "research", exact: true });
      await dialog.getByRole("button", { name: "Show more", exact: true }).click();
      await expect(dialog.getByRole("button", { name: "Show less", exact: true })).toBeVisible();
      const toggle = dialog.getByRole("switch", { name: "Use skill", exact: true });
      await expect(toggle).toBeChecked();
      await dialog.getByText("Use skill", { exact: true }).click();
      const error = dialog.getByRole("alert").filter({ hasText: "Fixture skill.update failed" });
      await expect(error).toBeInViewport();
      await expect(toggle).toBeChecked();
      await page.screenshot({ path: info.outputPath("skill-toggle-error.png"), animations: "disabled" });
      await dialog.getByText("Use skill", { exact: true }).click();
      await expect(toggle).not.toBeChecked();
      await dialog.getByRole("button", { name: "Skill instructions", exact: true }).click();
      await expect(dialog.locator("pre")).toContainText("Keep evidence with each conclusion");
      await dialog.getByRole("button", { name: "Delete", exact: true }).click();
      const confirmation = page.getByRole("alertdialog", { name: "Delete research?", exact: true });
      await confirmation.getByRole("button", { name: "Delete skill", exact: true }).click();
      await expect(confirmation.getByRole("alert")).toContainText("Fixture skill.delete failed");
      await expect(confirmation.getByRole("alert")).toBeInViewport();
      await page.screenshot({ path: info.outputPath("skill-delete-error.png"), animations: "disabled" });
      await confirmation.getByRole("button", { name: "Delete skill", exact: true }).click();
      await expect(dialog).not.toBeVisible();
      await expect(
        page.getByRole("button", { name: "Open details for research", exact: true }),
      ).not.toBeVisible();
      await expect(page.getByRole("button", { name: "Open details for weather", exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(errors).toEqual([]);
    });
    test(`Skills discovery, install retry and retained history at ${width}px in ${theme}`, async ({
      page,
    }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/browser/fixture.html?case=skills-rebuild&lang=en&theme=${theme}`);
      await page.getByRole("tab", { name: "Discover", exact: true }).click();
      await expect(page.getByText("SkillHub: A provider supplied partial catalog data")).toBeVisible();
      await expect(
        page.getByRole("alert").filter({ hasText: "Fixture trend endpoint unavailable" }),
      ).toBeVisible();
      await page.getByRole("button", { name: "Retry trends", exact: true }).click();
      await expect(
        page.getByRole("alert").filter({ hasText: "Fixture trend endpoint unavailable" }),
      ).not.toBeVisible();
      if (width > 640)
        await expect(page.getByRole("img", { name: "8-week install trend", exact: true })).toBeVisible();
      await page.getByRole("radio", { name: "SkillHub", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "Install Paper reading", exact: true }),
      ).not.toBeVisible();
      await page.getByRole("radio", { name: "All", exact: true }).click();
      const search = page.getByRole("textbox", { name: "Search skills", exact: true });
      await search.fill("causal inference");
      await search.press("Enter");
      await expect(
        page.getByRole("heading", { name: "Results for “causal inference”", exact: true }),
      ).toBeVisible();
      await expect(page.getByRole("button", { name: "Install Paper reading", exact: true })).toBeVisible();
      await page.screenshot({
        path: info.outputPath("skill-marketplace.png"),
        animations: "disabled",
        fullPage: true,
      });
      await page.getByRole("button", { name: "Install Paper reading", exact: true }).click();
      const confirm = page.getByRole("alertdialog", { name: "Install Paper reading?", exact: true });
      await confirm.getByRole("button", { name: "Install skill", exact: true }).click();
      await expect(confirm.getByRole("alert")).toContainText("Fixture skill.install failed");
      await expect(confirm.getByRole("alert")).toBeInViewport();
      await page.screenshot({ path: info.outputPath("skill-install-error.png"), animations: "disabled" });
      await confirm.getByRole("button", { name: "Install skill", exact: true }).click();
      await expect(confirm).not.toBeVisible();
      await expect(page.getByRole("button", { name: "Installed Paper reading", exact: true })).toBeDisabled();
      await page.getByRole("tab", { name: "Installed", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "Open details for paper-reading", exact: true }),
      ).toBeVisible();
      await page.getByRole("tab", { name: "Validation & history", exact: true }).click();
      await page.getByRole("textbox").fill("research");
      await page.getByRole("button", { name: "Validate", exact: true }).click();
      const version = page.getByRole("button", { name: "snapshot-20261107", exact: true });
      await expect(version).toBeVisible();
      await version.click();
      await expect(
        page.getByText("/home/skills/.history/research/snapshot-20261107", { exact: true }),
      ).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(errors).toEqual([]);
    });
  }
