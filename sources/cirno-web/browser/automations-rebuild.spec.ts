import { expect, test } from "@playwright/test";

for (const width of [390, 1440])
  for (const theme of ["light", "dark"]) {
    test(`Automation editing preserves precise schedules and retry drafts at ${width}px in ${theme}`, async ({
      page,
    }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await page.goto(
        `/browser/fixture.html?case=automations-rebuild&lang=en&theme=${theme}`,
      );
      await page
        .getByRole("button", { name: "Edit automation", exact: true })
        .click();
      const editor = page.getByRole("dialog", {
        name: "Edit task",
        exact: true,
      });
      await expect(
        editor.getByRole("spinbutton", { name: /^Every/ }),
      ).toHaveValue("62500");
      await expect(
        editor.getByRole("button", { name: "Save", exact: true }),
      ).toBeDisabled();
      await editor
        .getByRole("textbox", { name: /^Name/ })
        .fill("Revised checkpoint");
      await editor.getByRole("button", { name: "Save", exact: true }).click();
      await expect(editor.getByRole("alert")).toContainText(
        "Fixture automation save failed",
      );
      await expect(editor.getByRole("alert")).toBeInViewport();
      await expect(editor.getByRole("textbox", { name: /^Name/ })).toHaveValue(
        "Revised checkpoint",
      );
      await page.screenshot({
        path: info.outputPath("automation-edit-error.png"),
        animations: "disabled",
      });
      await editor.getByRole("button", { name: "Save", exact: true }).click();
      await expect(editor).not.toBeVisible();
      await expect(page.getByTestId("automation-writes")).toHaveText(
        '[{"name":"Revised checkpoint"}]',
      );

      await page
        .getByRole("button", { name: "Edit automation", exact: true })
        .click();
      await editor.getByRole("tab", { name: "Once", exact: true }).click();
      const year = editor.getByRole("spinbutton", { name: /^year,/ });
      await year.fill("2035");
      await editor.getByRole("button", { name: /^Choose date/ }).click();
      await expect(page.getByRole("grid")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("grid")).not.toBeVisible();
      await expect(editor).toBeVisible();
      await year.focus();
      await page.keyboard.press("Backspace");
      await expect(
        editor.getByRole("button", { name: "Save", exact: true }),
      ).toBeDisabled();
      await year.fill("2035");
      await expect(
        editor.getByRole("button", { name: "Save", exact: true }),
      ).toBeEnabled();
      await editor.getByRole("button", { name: "Save", exact: true }).click();
      await expect(editor).not.toBeVisible();
      const writes = JSON.parse(
        await page.getByTestId("automation-writes").innerText(),
      );
      expect(writes[1].schedule.kind).toBe("at");
      expect(new Date(writes[1].schedule.at_ms).getFullYear()).toBe(2035);

      await page
        .getByRole("button", { name: "Delete automation", exact: true })
        .click();
      const confirmation = page.getByRole("alertdialog");
      await confirmation
        .getByRole("button", { name: "Delete", exact: true })
        .click();
      await expect(confirmation.getByRole("alert")).toContainText(
        "Fixture automation delete failed",
      );
      await confirmation
        .getByRole("button", { name: "Delete", exact: true })
        .click();
      await expect(confirmation).not.toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      expect(errors).toEqual([]);
    });
  }
