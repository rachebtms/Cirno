import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";

async function keyboard(page: Page, height: number) {
  await page.evaluate(value => {
    Object.assign(window.visualViewport!, { height: value });
    window.visualViewport!.dispatchEvent(new Event("resize"));
  }, height);
}

async function backend(page: Page, olderWindow = false) {
  let socket: WebSocketRoute;
  let edited = false;
  const input = (text: string, turn = "original") => ({
    event: "user_message", chat_id: "mobile-edit", text, turn_id: turn, turn_seq: 0,
    projection_id: `user-${turn}`, starts_turn: true,
  });
  const events = () => edited ? [input("Edited request 中文", "revised")] : [input("Original request"),
    { event: "message", chat_id: "mobile-edit", text: "Original answer", turn_id: "original", turn_seq: 1,
      projection_id: "answer-original" },
    { event: "turn_end", chat_id: "mobile-edit", turn_id: "original", turn_seq: 2 }];
  await page.addInitScript(() => {
    Object.defineProperty(window, "visualViewport", { value: Object.assign(new EventTarget(), {
      height: 844, width: 390, offsetTop: 0, offsetLeft: 0, scale: 1,
    }) });
  });
  await page.route("**/v0/**", route => {
    const url = new URL(route.request().url()), path = url.pathname;
    if (path.endsWith("/webui-thread")) return route.fulfill({ json: {
      schemaVersion: 3, projection: "events", sessionKey: "websocket:mobile-edit", events: olderWindow && !edited && !url.searchParams.has("after")
        ? [input("Latest request", "latest")] : events(),
      completed_turn_ids: edited ? [] : ["original"], has_pending_tool_calls: false,
      page: { has_more_before: false, has_more_after: false, user_message_offset: 0 },
    } });
    if (path.endsWith("/prompts")) return route.fulfill({ json: {
      prompts: olderWindow && !edited ? [{ id: "user-original", index: 0, preview: "Original request",
        answerPreview: "Original answer", turnId: "original", cursor: "original-cursor", createdAt: 1 }] : [],
      offset: 0, total: olderWindow && !edited ? 1 : 0, count: olderWindow && !edited ? 1 : 0,
      revision: edited ? "2" : "1",
    } });
    if (path.endsWith("/commands")) return route.fulfill({ json: { commands: [] } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.routeWebSocket("**/mobile-edit-fixture-ws", wire => {
    socket = wire;
    wire.onMessage(raw => {
      const frame = JSON.parse(raw.toString());
      if (frame.type === "attach") wire.send(JSON.stringify({ event: "attached", chat_id: frame.chat_id }));
      if (frame.type !== "webui_request") return;
      if (frame.action === "instance.action" && frame.payload.action === "conversations.edit") {
        edited = true;
        // Match the server: reset precedes the action acknowledgement.
        wire.send(JSON.stringify({ event: "session_updated", chat_id: "mobile-edit", scope: "reset" }));
        wire.send(JSON.stringify({ ...input("Edited request 中文", "revised"), starts_turn: false }));
        // A fast model can reply before the action acknowledgement reaches the UI.
        wire.send(JSON.stringify({ event: "message", chat_id: "mobile-edit", turn_id: "revised",
          turn_seq: 1, text: "Early revised answer" }));
        wire.send(JSON.stringify({ event: "webui_response", request_id: frame.request_id, ok: true,
          result: { ok: true, turn_id: "revised" } }));
      } else wire.send(JSON.stringify({ event: "webui_response", request_id: frame.request_id, ok: true,
        result: { context_tokens: 1200, context_window_tokens: 128000, estimated: true } }));
    });
    wire.send(JSON.stringify({ event: "ready", chat_id: "mobile-edit", client_id: "fixture" }));
  });
  return { reply: () => socket.send(JSON.stringify({
    event: "message", chat_id: "mobile-edit", turn_id: "revised", turn_seq: 2, text: "Revised answer",
  })) };
}

for (const browserName of ["chromium", "webkit"] as const) {
  test(`${browserName}: mobile keyboard frees chrome, inline editing preserves main draft and replacement`, async ({ playwright }) => {
    const browser = await playwright[browserName].launch();
    const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    try {
      const api = await backend(page);
      await page.goto("/browser/fixture.html?case=mobile-editing&lang=en&theme=dark");
      await expect(page.getByText("Original request", { exact: true })).toBeVisible();
      const main = page.getByRole("textbox", { name: "Message input", exact: true });
      const tabs = page.locator(".workbench-group-bar"), launcher = page.locator(".workbench-launcher");
      await expect(tabs).toBeVisible();
      await main.fill("Retained main draft 中文");
      await keyboard(page, 390);
      await expect(tabs).toBeHidden();
      await expect(launcher).toBeHidden();
      await keyboard(page, 844);
      await expect(tabs).toBeVisible();
      await expect(launcher).toBeVisible();
      await page.getByRole("button", { name: "Edit message", exact: true }).click();
      const editor = page.getByRole("textbox", { name: "Edited message", exact: true });
      await expect(editor).toBeFocused();
      await keyboard(page, 390);
      await expect(main).toBeHidden();
      await editor.fill("Edited request 中文");
      await expect(editor).toHaveValue("Edited request 中文");
      await expect(page.getByRole("button", { name: "Save and send" })).toBeInViewport();
      await page.screenshot({ path: test.info().outputPath(`${browserName}-mobile-edit.png`) });
      await page.getByRole("button", { name: "Cancel", exact: true }).click();
      await keyboard(page, 844);
      await expect(main).toBeVisible();
      await expect(main).toHaveValue("Retained main draft 中文");
      await page.getByRole("button", { name: "Edit message", exact: true }).click();
      await editor.fill("Edited request 中文");
      await page.getByRole("button", { name: "Save and send" }).click();
      await expect(editor).toHaveCount(0);
      await expect(page.getByText("Edited request 中文", { exact: true })).toBeVisible();
      await expect(page.getByText("Early revised answer", { exact: true })).toBeVisible();
      api.reply();
      await expect(page.getByText("Revised answer", { exact: true })).toBeVisible();
      await expect(page.getByText("Edited request 中文", { exact: true })).toBeVisible();
      await expect(page.getByText("Original answer", { exact: true })).toHaveCount(0);
      await expect(main).toHaveValue("Retained main draft 中文");
    } finally { await browser.close(); }
  });
}


test("desktop: editing from an older history page returns to the rewritten latest history", async ({ page }) => {
  await backend(page, true);
  const messages = page.getByTestId("thread-message-region");
  await page.goto("/browser/fixture.html?case=mobile-editing&lang=en&theme=dark");
  await expect(messages.getByText("Latest request", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Message navigation", exact: true }).click();
  await page.locator("[data-prompt-row]").filter({ hasText: "Original request" }).click();
  await expect(messages.getByText("Original request", { exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Edit message", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Message input", exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Edited message", exact: true }).fill("Edited request 中文");
  await page.getByRole("button", { name: "Save and send" }).click();
  await expect(messages.getByText("Edited request 中文", { exact: true })).toBeVisible();
  await expect(messages.getByText("Early revised answer", { exact: true })).toBeVisible();
  await expect(messages.getByText("Original request", { exact: true })).toHaveCount(0);
  await expect(messages.getByText("Original answer", { exact: true })).toHaveCount(0);
  await expect(page.locator(".workbench-group-bar")).toBeVisible();
  await expect(page.locator(".workbench-launcher")).toBeVisible();
});
