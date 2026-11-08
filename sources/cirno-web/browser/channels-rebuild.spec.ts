import { expect, test } from "@playwright/test";
for (const width of [390, 1440])
  for (const theme of ["light", "dark"]) {
    test(`Channel catalog and draft completion at ${width}px in ${theme}`, async ({
      page,
    }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await page.goto(
        `/browser/fixture.html?case=channels-rebuild&loading&lang=en&theme=${theme}`,
      );
      await expect(
        page.getByRole("status", { name: "Loading channels…", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", {
          name: "View Telegram settings",
          exact: true,
        }),
      ).not.toBeVisible();
      await page
        .getByRole("button", { name: "Finish catalog loading", exact: true })
        .click();
      await expect(
        page.getByRole("status", { name: "Loading channels…", exact: true }),
      ).not.toBeVisible();
      await expect(
        page.getByRole("radio", { name: "All", exact: true }),
      ).toBeChecked();
      await expect(
        page.getByRole("switch", { name: "Cirno Web channel", exact: true }),
      ).toBeDisabled();
      const search = page.getByRole("searchbox", {
        name: "Search channels",
        exact: true,
      });
      await search.fill("no-match");
      await expect(
        page.getByText("No matching channels", { exact: true }),
      ).toBeVisible();
      await search.fill("telegram");
      const open = page.getByRole("button", {
        name: "View Telegram settings",
        exact: true,
      });
      await open.click();
      const dialog = page.getByRole("dialog", {
        name: "Channel setup",
        exact: true,
      });
      await expect(dialog).toBeVisible();
      const token = dialog.getByLabel("Bot token", { exact: true });
      await token.fill("fixture-only-token");
      await token.press("Tab");
      await expect(
        dialog.getByText("Fixture channel draft save failed", { exact: true }),
      ).toBeVisible();
      await page.screenshot({
        path: info.outputPath("channel-draft-failure.png"),
        fullPage: true,
        animations: "disabled",
      });
      await dialog.getByRole("button", { name: "Close", exact: true }).click();
      await expect(dialog).not.toBeVisible();
      await expect(open).toBeFocused();
      expect(await page.getByTestId("channel-writes").textContent()).toContain(
        "settings.channel.configure",
      );
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      expect(errors).toEqual([]);
    });
  }
for (const width of [390, 1440])
  test(`Channel installation retry and restart at ${width}px`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(
      `/browser/fixture.html?case=channels-rebuild&lang=en&theme=dark`,
    );
    const group = page.getByRole("region", {
      name: "Requires dependencies",
      exact: true,
    });
    await group
      .getByRole("button", { name: "Install Research connection", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "Fixture channel installation failed",
    );
    await group
      .getByRole("button", { name: "Install Research connection", exact: true })
      .click();
    await expect(
      page.getByText("Restart cirno to apply updated channel support.", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("switch", { name: "Cirno Web channel", exact: true }),
    ).toBeDisabled();
    await page.screenshot({
      path: info.outputPath("channel-restart.png"),
      fullPage: true,
      animations: "disabled",
    });
    await group
      .getByRole("button", { name: "Restart cirno", exact: true })
      .click();
    await expect(
      group.getByRole("switch", {
        name: "Research connection channel",
        exact: true,
      }),
    ).toBeEnabled();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });

test("Enter saves credentials without enabling the connection", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto(
    "/browser/fixture.html?case=channels-rebuild&lang=en&theme=light",
  );
  await page
    .getByRole("button", { name: "View Telegram settings", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
      name: "Channel setup",
      exact: true,
    }),
    token = dialog.getByLabel("Bot token", { exact: true });
  await dialog.getByRole("button", { name: "Advanced", exact: true }).click();
  const interval = dialog.getByRole("spinbutton", {
    name: "Update interval (seconds)",
    exact: true,
  });
  await expect(interval).toHaveValue("0.6");
  await expect(interval).toHaveAttribute("inputmode", "decimal");
  expect(
    await interval.evaluate((input: HTMLInputElement) => input.validity.valid),
  ).toBe(true);
  await token.fill("fixture-only-token");
  await token.press("Enter");
  await expect(dialog.getByRole("alert")).toContainText(
    "Fixture channel draft save failed",
  );
  await expect(token).toHaveValue("fixture-only-token");
  await token.press("Enter");
  await expect(token).toHaveValue("");
  await expect(token).toHaveAttribute("placeholder", "Saved secret");
  await expect(
    dialog.getByRole("switch", { name: "Enable channel", exact: true }),
  ).not.toBeChecked();
  expect(
    JSON.parse((await page.getByTestId("channel-writes").textContent())!),
  ).toEqual(["settings.channel.configure", "settings.channel.configure"]);
});

for (const width of [390, 1440])
  for (const action of ["check", "enable"]) {
    test(`First ${action} click follows credential autosave at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/browser/fixture.html?case=channels-rebuild&lang=en&theme=light&accept-save&slow-save");
      await page.getByRole("button", { name: "View Telegram settings", exact: true }).click();
      const dialog = page.getByRole("dialog", { name: "Channel setup", exact: true });
      await dialog.getByLabel("Bot token", { exact: true }).fill("fixture-only-token");
      if (action === "check")
        await dialog.getByRole("button", { name: "Check connection", exact: true }).click();
      else await dialog.getByText("Enable channel", { exact: true }).click();
      await expect(page.getByTestId("channel-writes")).toHaveText(JSON.stringify([
        "settings.channel.configure", "settings.channel.validate",
        ...(action === "enable" ? ["settings.channel.configure"] : []),
      ]));
      const toggle = dialog.getByRole("switch", { name: "Enable channel", exact: true });
      await expect(toggle).toBeEnabled();
      if (action === "enable") await expect(toggle).toBeChecked();
      else await expect(toggle).not.toBeChecked();
    });
  }

test("Failed credential save keeps the enable intent uncommitted and permits retry", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/browser/fixture.html?case=channels-rebuild&lang=en&theme=dark&slow-save");
  await page.getByRole("button", { name: "View Telegram settings", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Channel setup", exact: true });
  await dialog.getByLabel("Bot token", { exact: true }).fill("fixture-only-token");
  await dialog.getByText("Enable channel", { exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Fixture channel draft save failed");
  await expect(dialog.getByRole("switch", { name: "Enable channel", exact: true })).not.toBeChecked();
  await expect(page.getByTestId("channel-writes")).toHaveText(JSON.stringify(["settings.channel.configure"]));
  await dialog.getByText("Enable channel", { exact: true }).click();
  await expect(page.getByTestId("channel-writes")).toHaveText(JSON.stringify([
    "settings.channel.configure", "settings.channel.configure", "settings.channel.validate", "settings.channel.configure",
  ]));
  await expect(dialog.getByRole("switch", { name: "Enable channel", exact: true })).toBeEnabled();
  await expect(dialog.getByRole("switch", { name: "Enable channel", exact: true })).toBeChecked();
});
