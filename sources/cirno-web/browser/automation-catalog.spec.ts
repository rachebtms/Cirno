import { expect, test } from "@playwright/test";

for (const width of [390, 1440])
  for (const theme of ["light", "dark"]) {
    test(`Automation catalog shares native inspection and editing at ${width}px in ${theme}`, async ({
      page,
    }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await page.goto(
        `/browser/fixture.html?case=automation-catalog&lang=en&theme=${theme}`,
      );
      await expect(
        page.getByRole("heading", { name: "Automations", exact: true }),
      ).toHaveCount(1);
      await expect(
        page.getByRole("tab", { name: "Calendar", exact: true }),
      ).toHaveAttribute("aria-selected", "true");
      await expect(
        page.getByRole("button", { name: /System Heartbeat/ }),
      ).toHaveCount(0);
      const recorded = page.getByRole("button", {
        name: /^Research checkpoint,.*Completed/,
      });
      await recorded.click();
      const run = page.getByRole("dialog", {
        name: "Research checkpoint",
        exact: true,
      });
      await expect(
        run.getByRole("link", { name: "Open a chat", exact: true }),
      ).toHaveAttribute("href", "#/chat/websocket%3Aoriginal-research");
      await expect(run).toContainText("0 sec");
      await page.keyboard.press("Escape");
      await expect(run).not.toBeVisible();
      await expect(recorded).toBeFocused();
      if (width === 1440) {
        const overflow = page.getByRole("button", {
          name: "+1 more",
          exact: true,
        });
        await overflow.click();
        await page
          .getByRole("button", { name: /^Failed experiment,.*Planned/ })
          .click();
        const failed = page.getByRole("dialog", {
          name: "Failed experiment",
          exact: true,
        });
        await expect(failed.getByRole("alert")).toContainText(
          "SSH connection dropped",
        );
        await page.keyboard.press("Escape");
        await expect(failed).not.toBeVisible();
        await expect(overflow).toBeFocused();
      }
      await page.screenshot({
        path: info.outputPath("automation-calendar.png"),
        animations: "disabled",
      });
      await page.getByRole("tab", { name: "Tasks", exact: true }).click();
      await page.getByRole("button", { name: /^Research checkpoint/ }).click();
      const detail = page.getByRole("dialog", {
        name: "Research checkpoint",
        exact: true,
      });
      await detail
        .getByRole("button", { name: "Show full message", exact: true })
        .click();
      await detail
        .getByRole("button", { name: "Task information", exact: true })
        .click();
      const information = page.getByRole("dialog", {
        name: "Task information",
        exact: true,
      });
      await expect(information).toContainText("62,500 milliseconds");
      await page.keyboard.press("Escape");
      await expect(information).not.toBeVisible();
      await expect(detail).toBeVisible();
      await detail.getByRole("button", { name: "Edit", exact: true }).click();
      const edit = page.getByRole("dialog", { name: "Edit task", exact: true });
      await expect(edit).toBeVisible();
      await expect(page.getByRole("dialog")).toHaveCount(1);
      await edit.getByRole("button", { name: "Cancel", exact: true }).click();
      await expect(detail).toBeVisible();
      await expect(page.getByRole("dialog")).toHaveCount(1);
      await page.screenshot({
        path: info.outputPath("automation-detail.png"),
        animations: "disabled",
      });
      await page.keyboard.press("Escape");
      await expect(detail).not.toBeVisible();
      await page.getByRole("button", { name: "Filter", exact: true }).click();
      await page.getByRole("menuitemradio", { name: /^Active/ }).click();
      await expect(
        page.getByRole("button", { name: /^Paused review/ }),
      ).toHaveCount(0);
      await page.getByRole("button", { name: /^Research checkpoint/ }).click();
      await detail
        .getByRole("button", { name: "More actions", exact: true })
        .click();
      await page
        .getByRole("menuitem", { name: "Disable", exact: true })
        .click();
      await expect(detail).toBeVisible();
      await detail.getByRole("button", { name: "Close", exact: true }).click();
      await expect(detail).not.toBeVisible();
      await expect(
        page.getByRole("button", { name: /^Research checkpoint/ }),
      ).toHaveCount(0);
      await expect(page.getByTestId("automation-actions")).toContainText(
        "disable:daily",
      );

      await page
        .getByRole("button", { name: "Session details", exact: true })
        .click();
      await page.getByRole("button", { name: /^GPU availability,/ }).click();
      const trigger = page.getByRole("dialog", {
        name: "GPU availability",
        exact: true,
      });
      await expect(trigger).toContainText("nvidia-smi");
      await expect(
        trigger.getByRole("button", { name: "Run now", exact: true }),
      ).toHaveCount(0);
      await page.keyboard.press("Escape");
      await expect(trigger).not.toBeVisible();
      await expect(
        page.getByRole("button", { name: "Session details", exact: true }),
      ).toBeFocused();
      await page.getByRole("button", { name: /Filter: Active/ }).click();
      await page.getByRole("menuitemradio", { name: /^All/ }).click();
      await page.getByRole("button", { name: /^Paused review/ }).click();
      const paused = page.getByRole("dialog", {
        name: "Paused review",
        exact: true,
      });
      await paused
        .getByRole("button", { name: "More actions", exact: true })
        .click();
      await page.getByRole("menuitem", { name: "Delete", exact: true }).click();
      const confirmation = page.getByRole("alertdialog");
      await confirmation
        .getByRole("button", { name: "Delete", exact: true })
        .click();
      await expect(confirmation).not.toBeVisible();
      await expect(
        page.getByRole("button", { name: /^Paused review/ }),
      ).toHaveCount(0);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      expect(errors).toEqual([]);
    });
  }
