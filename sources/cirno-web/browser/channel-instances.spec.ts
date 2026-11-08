import { expect, test } from "@playwright/test";
for (const width of [390, 1440])
  test(`Instance rollback and draft handoff at ${width}px`, async ({
    page,
  }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto(
      `/browser/fixture.html?case=channel-instances&lang=en&theme=${width === 390 ? "light" : "dark"}`,
    );
    await page
      .getByRole("button", {
        name: "View Research connections settings",
        exact: true,
      })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "Channel setup",
      exact: true,
    });
    const first = dialog
        .locator("article")
        .filter({
          has: page.getByRole("heading", { name: "Worker A", exact: true }),
        }),
      second = dialog
        .locator("article")
        .filter({
          has: page.getByRole("heading", { name: "Worker B", exact: true }),
        });
    await first.getByRole("button", { name: "Advanced", exact: true }).click();
    await first.getByText("Us", { exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText(
      "Fixture instance save rejected",
    );
    await expect(
      first.getByRole("radio", { name: "Us", exact: true }),
    ).toBeChecked();
    await page.screenshot({
      path: info.outputPath("instance-draft-error.png"),
      fullPage: true,
      animations: "disabled",
    });
    await second.getByRole("button", { name: "Advanced", exact: true }).click();
    await expect(
      first.getByRole("radio", { name: "Us", exact: true }),
    ).not.toBeVisible();
    await expect(
      second.getByRole("radio", { name: "Us", exact: true }),
    ).toBeChecked();
    const writes = JSON.parse(
      (await page.getByTestId("instance-writes").textContent())!,
    );
    expect(
      writes.filter(
        (call: { action: string }) =>
          call.action === "settings.channel.configure",
      ),
    ).toEqual(
      Array(2).fill({
        action: "settings.channel.configure",
        payload: {
          name: "multiplugin",
          values: { "channels.multiplugin.region": "us" },
          enable: true,
          instance_id: "first",
        },
      }),
    );
    await first.locator('[data-slot="switch-content"]').click();
    await expect(dialog.getByRole("alert")).toContainText(
      "Fixture instance toggle rejected",
    );
    await expect(
      first.getByRole("switch", { name: "Worker A instance", exact: true }),
    ).toBeChecked();
    await first.locator('[data-slot="switch-content"]').click();
    await expect(
      first.getByRole("switch", { name: "Worker A instance", exact: true }),
    ).not.toBeChecked();
    await expect(
      first.getByRole("switch", { name: "Worker A instance", exact: true }),
    ).toBeEnabled();
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).not.toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
  });
