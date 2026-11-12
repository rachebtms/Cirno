import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { seedPreviewPreferences } from "./preference-driver";

for (const width of [390, 1440]) for (const locale of ["en", "zh-CN"]) {
  test(`checkpoint success with incomplete learning at ${width}px in ${locale}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await seedPreviewPreferences(page, { language: locale });
    const copy = JSON.parse(readFileSync(new URL(`../src/i18n/locales/${locale}/common.json`, import.meta.url), "utf8")).thread.compaction;
    const event = { event: "context_compaction", chat_id: "answer-order", compaction_id: "partial-learning", phase: "succeeded", reason: "manual",
      projection_id: "partial-learning", turn_id: "turn-learning", turn_seq: 1,
      learning_failure: { source: "source-1234567890abcdef1234567890abcdef12345678", error: "Could not save USER.md",
        saved: [{ id: "memory:0", kind: "memory", label: "Measured 43.2 K" }],
        pending: [{ id: "document:0", kind: "document", label: "USER.md" }] } };
    await page.route("**/v0/**", route => route.fulfill({ status: 404, json: {} }));
    await page.route("**/v0/commands", route => route.fulfill({ json: { commands: [] } }));
    await page.route("**/v0/sessions/*/webui-thread?*", route => route.fulfill({ json: {
      schemaVersion: 3, projection: "events", has_more: false, events: [event],
    } }));
    await page.routeWebSocket("**/answer-order-socket", route => route.onMessage(raw => {
      const frame = JSON.parse(String(raw));
      if (frame.type === "attach") route.send(JSON.stringify({ event: "attached", chat_id: frame.chat_id }));
    }));
    await page.goto("/browser/fixture.html?case=answer-order");
    const notice = page.locator('[data-context-compaction="succeeded"]');
    await expect(notice).toContainText(copy.learningFailed);
    await notice.locator("summary").click();
    await expect(notice).toContainText(copy.learningPending);
    await expect(notice).toContainText("USER.md");
    await expect(notice).toContainText("43.2 K");
    await expect(notice).toContainText(`/consolidate retry ${event.learning_failure.source}`);
    expect(await notice.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
    await page.screenshot({ path: info.outputPath("learning-incomplete.png") });
    await page.reload();
    await expect(notice).toContainText(copy.learningFailed);
  });
}
