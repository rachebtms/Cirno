import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { seedPreviewPreferences } from "./preference-driver";

for (const width of [390, 1440]) for (const locale of ["en", "zh-CN"]) for (const outcome of ["completed", "no_updates", "incomplete", "not_found"] as const) {
  test(`learning retry ${outcome} at ${width}px in ${locale}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await seedPreviewPreferences(page, { language: locale, themeMode: locale === "zh-CN" ? "dark" : "light" });
    const copy = JSON.parse(readFileSync(new URL(`../src/i18n/locales/${locale}/common.json`, import.meta.url), "utf8")).thread.compaction;
    const source = "source-1234567890abcdef1234567890abcdef12345678";
    const proposed = Array.from({ length: 4 }, (_, i) => ({ id: `memory:${i}`, kind: "memory", label: `Verified research lesson ${i + 1}` }));
    const report = { source, mode: outcome === "no_updates" ? "regenerate" : outcome === "not_found" ? "none" : "replay", outcome,
      model_called: outcome === "no_updates", requested: outcome === "not_found" ? [] : proposed,
      saved: outcome === "completed" ? proposed : outcome === "incomplete" ? proposed.slice(0, 1) : [],
      previously_saved: outcome === "incomplete" ? proposed.slice(0, 1) : [],
      pending: outcome === "incomplete" ? proposed.slice(1) : [],
    };
    const event = { event: "context_compaction", chat_id: "answer-order", compaction_id: "learning-retry", phase: outcome === "incomplete" ? "failed" : "succeeded", reason: "manual",
      projection_id: "retry-result", turn_id: "retry-turn", turn_seq: 1, learning_retry: report,
      ...(outcome === "incomplete" ? { error: "Could not save remaining updates" } : {}),
    };
    const user = { event: "user_message", chat_id: "answer-order", turn_id: "retry-turn", projection_id: "retry-user", text: `/consolidate retry ${source}`, starts_turn: false };
    await page.route("**/v0/**", route => route.fulfill({ status: 404, json: {} }));
    await page.route("**/v0/commands", route => route.fulfill({ json: { commands: [{ command: "/consolidate", title: "Consolidate", description: "Consolidate", icon: "archive", accepts_args: true, lifecycle: "side_channel", arg_hint: "[retry [source-id]]" }] } }));
    await page.route("**/v0/sessions/*/webui-thread?*", route => route.fulfill({ json: { schemaVersion: 3, projection: "events", has_more: false, events: [user, event] } }));
    await page.routeWebSocket("**/answer-order-socket", route => route.onMessage(raw => {
      const frame = JSON.parse(String(raw));
      if (frame.type === "attach") route.send(JSON.stringify({ event: "attached", chat_id: frame.chat_id }));
    }));
    await page.goto("/browser/fixture.html?case=answer-order");
    if (locale === "zh-CN") await expect(page.locator("html")).toHaveClass(/dark/);
    const notice = page.locator("[data-context-compaction]");
    const title = copy.retry[outcome === "incomplete" ? "failed" : outcome];
    await expect(page.getByTestId("message-slash-command")).toHaveText("/consolidate");
    await expect(notice).toContainText(title);
    await notice.locator("summary").click();
    await expect(notice).toContainText(source);
    await expect(notice).toContainText(copy.retry.checkpointUnchanged);
    if (outcome === "completed") await expect(notice).toContainText(proposed[3].label);
    if (outcome === "no_updates") {
      await expect(notice).toContainText(copy.retry.noUpdatesHelp);
      await expect(notice).toContainText(copy.retry.originalProposals);
    }
    if (outcome === "incomplete") await expect(notice).toContainText("Could not save remaining updates");
    if (outcome === "not_found") await expect(notice).toContainText(copy.retry.notFoundHelp);
    expect(await notice.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
    await page.screenshot({ path: info.outputPath("learning-retry.png") });
    await page.reload();
    await expect(notice).toContainText(title);
    await notice.locator("summary").click();
    await expect(notice).toContainText(source);
    await expect(page.getByTestId("message-slash-command")).toHaveText("/consolidate");
  });
}
