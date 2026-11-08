import { expect, test } from "@playwright/test";
for (const width of [390, 1440])
  for (const theme of ["light", "dark"]) {
    test(`Telegram pairing, cancellation and reconnect at ${width}px in ${theme}`, async ({ page }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/browser/fixture.html?case=telegram-rebuild&lang=en&theme=${theme}`);
      await expect(page.getByRole("alert")).toContainText("Fixture Telegram status offline");
      await page.getByRole("button", { name: "Retry", exact: true }).click();
      await page.getByRole("button", { name: "Generate PIN", exact: true }).click();
      await expect(page.getByRole("alert")).toContainText("Fixture PIN generation failed");
      await page.getByRole("button", { name: "Generate PIN", exact: true }).click();
      await expect(page.getByLabel("Pairing PIN", { exact: true })).toHaveText("12345678");
      await page.getByRole("button", { name: "Refresh PIN", exact: true }).click();
      await expect(page.getByLabel("Pairing PIN", { exact: true })).toHaveText("87654321");
      await page.screenshot({
        path: info.outputPath("telegram-pin.png"),
        animations: "disabled",
        fullPage: true,
      });
      await page.getByRole("button", { name: "Cancel", exact: true }).click();
      await expect(page.getByRole("alert")).toContainText("Fixture Telegram disconnect failed");
      await expect(page.getByLabel("Pairing PIN", { exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Cancel", exact: true }).click();
      await expect(page.getByLabel("Pairing PIN", { exact: true })).not.toBeVisible();
      await page.getByRole("button", { name: "Generate PIN", exact: true }).click();
      await page.getByRole("button", { name: "Simulate Telegram verification", exact: true }).click();
      await expect(page.getByRole("heading", { name: "@fixture_owner", exact: true })).toBeVisible();
      await expect(page.getByLabel("Pairing PIN", { exact: true })).not.toBeVisible();
      await expect(page.getByRole("button", { name: "Disconnect", exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Configure bot", exact: true }).click();
      await expect(page.getByText("Fixture channel setup requested")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(errors).toEqual([]);
    });
    test(`Telegram URL drafts and notification settings at ${width}px in ${theme}`, async ({
      page,
    }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/browser/fixture.html?case=telegram-rebuild&lang=en&theme=${theme}`);
      await page.getByRole("button", { name: "Retry", exact: true }).click();
      const url = page.getByRole("textbox", { name: "Web UI address (optional)", exact: true });
      await url.fill("invalid url");
      await page.getByRole("button", { name: "Save", exact: true }).click();
      expect(await url.evaluate((input: HTMLInputElement) => input.validity.valid)).toBe(false);
      await expect(url).toHaveAttribute("aria-invalid", "true");
      expect(
        JSON.parse((await page.getByTestId("telegram-actions").textContent())!).filter(
          (call: { action: string }) => call.action === "telegram.settings",
        ),
      ).toHaveLength(0);
      await url.fill("https://cirno.example/research");
      await page.getByRole("button", { name: "Save", exact: true }).click();
      await expect(page.getByRole("alert")).toContainText("Fixture Telegram settings failed");
      await expect(url).toHaveValue("https://cirno.example/research");
      await page.screenshot({
        path: info.outputPath("telegram-url-error.png"),
        animations: "disabled",
        fullPage: true,
      });
      await page.getByRole("button", { name: "Save", exact: true }).click();
      await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
      await page.getByText("Actions", { exact: true }).click();
      await expect(page.getByRole("switch", { name: "Actions", exact: true })).not.toBeChecked();
      await page.getByText("Enable Telegram", { exact: true }).click();
      await expect(page.getByRole("switch", { name: "Router messages", exact: true })).toBeDisabled();
      await page.getByText("Enable Telegram", { exact: true }).click();
      await expect(page.getByRole("switch", { name: "Router messages", exact: true })).toBeEnabled();
      await expect(page.getByRole("switch", { name: "Actions", exact: true })).not.toBeChecked();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(errors).toEqual([]);
    });
  }
