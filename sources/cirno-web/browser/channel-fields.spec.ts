import { expect, test } from "@playwright/test";
for (const width of [390, 1440])
  test(`Native connection fields at ${width}px`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto(
      `/browser/fixture.html?case=channel-fields&lang=en&theme=${width === 390 ? "light" : "dark"}`,
    );
    const group = page.getByRole("radiogroup", { name: "Region", exact: true });
    await expect(
      group.getByRole("radio", { name: "Europe", exact: true }),
    ).toBeChecked();
    await group
      .getByRole("radio", { name: "Europe", exact: true })
      .press("ArrowRight");
    await expect(
      group.getByRole("radio", { name: "United States", exact: true }),
    ).toBeChecked();
    await page.getByText("Use proxy", { exact: true }).click();
    await expect(
      page.getByRole("switch", { name: "Use proxy", exact: true }),
    ).not.toBeChecked();
    await page
      .getByRole("button", { name: "Remove credentials", exact: true })
      .click();
    await expect(
      page.getByText("Will be removed", { exact: true }),
    ).toBeVisible();
    expect(
      JSON.parse((await page.getByTestId("field-payload").textContent())!),
    ).toMatchObject({ token: null, region: "us", useProxy: "false" });
    await page
      .getByRole("button", { name: "Keep credentials", exact: true })
      .click();
    expect(
      JSON.parse((await page.getByTestId("field-payload").textContent())!),
    ).not.toHaveProperty("token");
    const token = page.getByLabel("API token", { exact: true });
    await token.fill("fixture-only-token");
    await page
      .getByRole("button", { name: "Show secret", exact: true })
      .click();
    await expect(token).toHaveAttribute("type", "text");
    const json = page.getByRole("textbox", {
      name: "Connection options",
      exact: true,
    });
    await json.fill('{\n  "timeout": 45,\n  "env": {"LANG": "zh_CN.UTF-8"}\n}');
    await expect(json).toHaveValue(/"timeout": 45/);
    await page
      .getByRole("button", { name: "Validate fields", exact: true })
      .click();
    await expect(group).toHaveAttribute("aria-invalid", "true");
    await expect(
      group.getByRole("radio", { name: "Default", exact: true }),
    ).toBeFocused();
    await expect(token).toHaveAttribute("aria-invalid", "true");
    await page.screenshot({
      path: info.outputPath("channel-fields.png"),
      fullPage: true,
      animations: "disabled",
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
  });
