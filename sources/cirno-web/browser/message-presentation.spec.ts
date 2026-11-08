import { expect, test } from "@playwright/test";

for (const width of [390, 1440])
  for (const theme of ["light", "dark"]) {
    test(`Native message presentation at ${width}px in ${theme}`, async ({
      page,
    }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await page.goto(
        `/browser/fixture.html?case=message-presentation&lang=en&theme=${theme}`,
      );
      const mixed = page.getByRole("region", {
        name: "Mixed attachments",
        exact: true,
      });
      await expect(
        mixed.getByRole("img", { name: "plot.svg", exact: true }),
      ).toHaveCount(1);
      await expect(
        mixed.getByRole("link", {
          name: "Download measurements.csv",
          exact: true,
        }),
      ).toBeVisible();
      const video = mixed.getByLabel("Video attachment: experiment.webm", {
        exact: true,
      });
      await expect(video).toBeVisible();
      const source = page.getByRole("button", {
        name: "This reply switched to a fallback model, answered by Research backup.",
        exact: true,
      });
      await source.click();
      const description = page.getByRole("dialog", {
        name: "This reply switched to a fallback model, answered by Research backup.",
        exact: true,
      });
      await expect(description).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(description).not.toBeVisible();
      await page.mouse.move(0, 0);
      await page
        .getByRole("button", {
          name: "Not sent: Message too large",
          exact: true,
        })
        .click();
      const failure = page.getByRole("dialog", {
        name: "Message too large",
        exact: true,
      });
      await expect(failure).toContainText(
        "Remove some images or try smaller files",
      );
      await failure.getByRole("button", { name: "Close", exact: true }).click();
      await expect(failure).not.toBeVisible();
      const heartbeat = page.getByRole("region", {
        name: "System input",
        exact: true,
      });
      await expect(
        heartbeat.getByText("Inspect authorized research tasks.", {
          exact: true,
        }),
      ).toHaveCount(0);
      await heartbeat
        .getByRole("button", { name: "Heartbeat", exact: true })
        .click();
      await expect(
        heartbeat.getByText("Inspect authorized research tasks.", {
          exact: true,
        }),
      ).toBeVisible();
      await heartbeat
        .getByRole("button", { name: "Heartbeat", exact: true })
        .click();
      await page.screenshot({
        path: info.outputPath("message-presentation.png"),
        fullPage: true,
        animations: "disabled",
      });
      const history = page.getByRole("region", {
        name: "Large tool history",
        exact: true,
      });
      const toggle = history.getByRole("button", {
        name: "Used 10000 tools",
        exact: true,
      });
      const centers = await toggle
        .locator(":scope > svg, :scope > span")
        .evaluateAll((elements) =>
          elements.map((element) => {
            const box = element.getBoundingClientRect();
            return box.y + box.height / 2;
          }),
        );
      expect(Math.max(...centers) - Math.min(...centers)).toBeLessThan(2);
      await expect(history.getByRole("listitem")).toHaveCount(0);
      await toggle.click();
      await expect(history.getByRole("listitem")).toHaveCount(200);
      await history
        .getByRole("button", { name: "Show 200 more tool events", exact: true })
        .click();
      await expect(history.getByRole("listitem")).toHaveCount(400);
      await toggle.click();
      await expect(history.getByRole("listitem")).toHaveCount(0);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      expect(errors).toEqual([]);
    });
  }
