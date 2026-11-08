import { expect, test } from "@playwright/test";

for (const width of [390, 1440])
  for (const theme of ["light", "dark"]) {
    test(`Memory queries, historical evidence and retry at ${width}px in ${theme}`, async ({
      page,
    }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/browser/fixture.html?case=memory-rebuild&lang=en&theme=${theme}`);
      const search = page.getByRole("textbox", { name: "Search memories", exact: true });
      await search.fill("exact threshold");
      await page.getByRole("button", { name: "Search memories", exact: true }).click();
      await expect(page.getByRole("status")).toContainText("exact threshold");
      await search.fill("unsubmitted draft");
      await page.getByRole("button", { name: "Load more", exact: true }).click();
      await expect(page.getByRole("button", { name: "Follow-up measurement", exact: true })).toBeVisible();
      const calls = () =>
        page
          .getByTestId("memory-calls")
          .textContent()
          .then((text) => JSON.parse(text!));
      expect(
        (await calls()).findLast((call: { action: string }) => call.action === "memory.list").values,
      ).toMatchObject({ query: "exact threshold", offset: 10 });
      await page.getByRole("button", { name: /Search mode$/ }).click();
      await page.getByRole("option", { name: "Vector", exact: true }).click();
      await expect(page.getByText("Vector retrieval is disabled; using BM25.")).toBeVisible();
      await page.getByRole("button", { name: "Time filter", exact: true }).click();
      const years = page.getByRole("spinbutton", { name: /^year,/ });
      await expect(years.first()).toHaveText("yyyy");
      const months = page.getByRole("spinbutton", { name: /^month,/ });
      const days = page.getByRole("spinbutton", { name: /^day,/ });
      for (let i = 0; i < 2; i++) {
        await months.nth(i).fill("11");
        await days.nth(i).fill(i ? "7" : "1");
        await years.nth(i).fill("2026");
      }
      await page.getByRole("button", { name: /^Choose date/ }).first().click();
      await expect(page.getByRole("grid")).toBeVisible();
      await page.keyboard.press("Escape");
      await page.getByRole("button", { name: "Apply dates", exact: true }).click();
      await expect
        .poll(
          async () =>
            (await calls()).findLast((call: { action: string }) => call.action === "memory.list").values,
        )
        .toMatchObject({ since: "2026-11-01", until: "2026-11-07", time_field: "observed_at" });
      await page.getByRole("button", { name: "Browse tags", exact: true }).click();
      await page.getByRole("button", { name: "calibration · 12", exact: true }).click();
      await page.screenshot({
        path: info.outputPath("memory-library.png"),
        animations: "disabled",
        fullPage: true,
      });
      await page.getByRole("button", { name: "Detector calibration", exact: true }).click();
      const inspector = page.getByRole("dialog", { name: "Detector calibration", exact: true });
      await inspector.getByRole("tab", { name: "Versions", exact: true }).click();
      await inspector.getByRole("button", { name: "Version 1", exact: true }).click();
      await expect(inspector.getByText("Original temperature: 30.25 °C")).toBeVisible();
      await inspector.getByRole("tab", { name: "Source", exact: true }).click();
      const more = inspector.getByRole("button", { name: "Next source page", exact: true });
      await expect(more).toBeInViewport();
      await more.click();
      await expect(inspector.getByRole("alert")).toContainText("Evidence page temporarily unavailable");
      await expect(inspector.getByRole("alert")).toBeInViewport();
      await page.screenshot({ path: info.outputPath("memory-evidence-error.png"), animations: "disabled" });
      await inspector.getByRole("button", { name: "Retry", exact: true }).click();
      await expect(inspector.getByText(/Continuation: exact original measurement/)).toBeVisible();
      const sourceCalls = (await calls()).filter(
        (call: { action: string }) => call.action === "memory.source",
      );
      expect(sourceCalls.map((call: { values: unknown }) => call.values)).toEqual([
        { id: "calibration", revision: 1 },
        { id: "captured-source", revision: 7, start_line: 4, char_offset: 16000 },
        { id: "captured-source", revision: 7, start_line: 4, char_offset: 16000 },
      ]);
      await page.keyboard.press("Escape");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(errors).toEqual([]);
    });
    test(`Profile editing keeps a failed save draft at ${width}px in ${theme}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/browser/fixture.html?case=memory-rebuild&profile&lang=en&theme=${theme}`);
      await page.getByRole("button", { name: "Edit Router personality", exact: true }).click();
      const editor = page.getByRole("dialog", { name: "Router personality", exact: true });
      await editor.getByRole("textbox").fill("A precise personal research assistant.");
      await editor.getByRole("button", { name: "Save", exact: true }).click();
      await expect(editor.getByRole("alert")).toContainText("File changed; reload before saving");
      await expect(editor.getByRole("textbox")).toHaveValue("A precise personal research assistant.");
      await expect(editor.getByRole("button", { name: "Save", exact: true })).toBeInViewport();
      await page.screenshot({ path: info.outputPath("profile-edit-error.png"), animations: "disabled" });
      await editor.getByRole("button", { name: "Cancel", exact: true }).click();
      await expect(editor).not.toBeVisible();
    });
  }
