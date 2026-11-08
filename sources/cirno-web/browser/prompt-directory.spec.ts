import { expect, test } from "@playwright/test";

for (const width of [1440, 390]) test.describe(`paged prompt directory ${width}px`, () => {
  test.use({ viewport: { width, height: 900 }, isMobile: width < 600, hasTouch: width < 600 });
  test("searches 20k prompts and navigates to an unloaded page with bounded metadata", async ({ page }) => {
    const metadata: Array<{ offset: number; query: string; size: number }> = [];
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/v0/sessions/**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith("/prompts")) {
        const query = url.searchParams.get("q")?.toLowerCase() ?? "";
        const matches = Array.from({ length: 20000 }, (_, index) => index).filter((index) => `Question ${index}`.toLowerCase().includes(query));
        const offset = Math.min(matches.length, Number(url.searchParams.get("offset") ?? Math.max(0, matches.length - 64)));
        const indices = matches.slice(offset, offset + 64);
        metadata.push({ offset, query, size: indices.length });
        return route.fulfill({ json: { revision: "r1", count: 20000, total: matches.length, offset,
          prompts: indices.map((index) => ({ id: `u${index}`, index, preview: `Question ${index}`,
            answerPreview: "Research result", cursor: String(index), turnId: `t${index}`, createdAt: index + 1 })) } });
      }
      const start = url.searchParams.has("after") ? Number(url.searchParams.get("after")) : 19990;
      return route.fulfill({ json: { schemaVersion: 3, projection: "events",
        events: Array.from({ length: 10 }, (_, offset) => [
          { event: "user_message", chat_id: "rail", projection_id: `u${start + offset}`, text: `Question ${start + offset}`, starts_turn: true },
          { event: "message", chat_id: "rail", projection_id: `a${start + offset}`, text: "Research result.\n\n".repeat(8) },
        ]).flat(), page: { before_cursor: String(start), after_cursor: String(start + 10), user_message_offset: start,
          has_more_before: start > 0, has_more_after: start + 10 < 20000 } } });
    });
    await page.goto(`/browser/fixture.html?case=rail&real=1&directory=1&theme=${width < 600 ? "dark" : "light"}`);
    const body = page.getByTestId("thread-message-region");
    await expect(body.getByText("Question 19999", { exact: true })).toBeAttached();
    await expect.poll(() => metadata.length).toBeGreaterThan(0);
    expect(metadata.filter((read) => !read.query).length).toBeLessThanOrEqual(3);
    await page.getByRole("button", { name: "Message navigation", exact: true }).click();
    const dialog = page.getByRole("dialog");
    const search = dialog.getByRole("searchbox", { name: "Search messages" });
    await search.fill("Question 1234");
    const target = dialog.getByRole("button", { name: "Jump to message: Question 1234", exact: true });
    await expect(target).toBeVisible();
    await expect.poll(async () => {
      const box = await dialog.boundingBox();
      return box ? Math.abs(box.x + box.width - width) : width;
    }).toBeLessThan(1);
    await expect(dialog.getByRole("button", { name: "Close", exact: true })).toBeInViewport();
    expect(await dialog.locator("[data-prompt-row]").count()).toBeLessThan(25);
    await page.screenshot({ path: `test-results/prompt-directory-${width}-search.png` });
    await target.click();
    await expect(dialog).not.toBeVisible();
    await expect(body.getByText("Question 1234", { exact: true })).toBeInViewport();
    expect(await body.locator("[data-user-prompt-id]").count()).toBeLessThanOrEqual(24);
    expect(metadata.every((read) => read.size <= 64)).toBe(true);
    expect(metadata.reduce((sum, read) => sum + read.size, 0)).toBeLessThan(1000);
    expect(errors).toEqual([]);
    await page.screenshot({ path: `test-results/prompt-directory-${width}-jump.png` });
  });
});
