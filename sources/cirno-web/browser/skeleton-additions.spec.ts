import { readPreviewPreferences } from "./preference-driver";
import { expect, test, type Locator, type Page } from "@playwright/test";

const fixture = (surface: string, state = "loaded", extra = "") => `/browser/fixture.html?case=skeleton-additions&surface=${surface}&state=${state}${extra}`;
const status = (page: Page) => page.locator('[role="status"][aria-busy="true"]');

async function settle(page: Page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(document.getAnimations().filter((animation) => animation.effect?.getTiming().iterations !== Infinity)
      .map((animation) => animation.finished.catch(() => {})));
  });
}

async function boxes(locator: Locator) {
  await expect(locator.first()).toBeVisible();
  return locator.evaluateAll((elements) => elements.map((element) => {
    const { x, y, width, height } = element.getBoundingClientRect();
    return { x, y, width, height };
  }));
}

function sameBoxes(actual: Awaited<ReturnType<typeof boxes>>, expected: typeof actual, surface = "") {
  expect(actual).toHaveLength(expected.length);
  for (let index = 0; index < actual.length; index++) for (const key of ["x", "y", "width", "height"] as const) {
    expect(Math.abs(actual[index][key] - expected[index][key]), `${surface} row ${index} ${key}: ${JSON.stringify({ actual: actual[index], expected: expected[index] })}`).toBeLessThan(0.5);
  }
}

async function accessibleSkeleton(page: Page) {
  await expect(status(page).first()).toBeVisible();
  expect(await status(page).first().getAttribute("aria-label")).toBeTruthy();
  await expect(status(page).first().locator(".animate-pulse")).toHaveAttribute("aria-hidden", "true");
  expect(await status(page).first().locator(".animate-pulse").evaluate((element) => getComputedStyle(element).animationName)).toBe("none");
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
}

for (const width of [390, 1440]) for (const locale of ["en", "zh-CN"]) {
  test.describe(`${width}px ${locale} new first-load skeletons`, () => {
    test.use({ viewport: { width, height: 1000 }, reducedMotion: "reduce", hasTouch: width === 390, locale });
    test.beforeEach(async ({ page }) => {
      await page.clock.setFixedTime(new Date("2026-10-19T12:00:00Z"));
    });

    test("the catalog keeps its heading while loading without displaying fake conversations", async ({ page }) => {
      await page.goto(fixture("chats", "loaded"));
      const catalog = page.getByRole("region", { name: locale === "en" ? "Conversations" : "会话列表", exact: true });
      await expect(catalog.locator("[data-chat-row]")).toHaveCount(4);
      const heading = await catalog.getByRole("heading", { level: 1 }).boundingBox();
      await page.goto(fixture("chats", "loading"));
      await expect(catalog).toHaveAttribute("aria-busy", "true");
      await expect(catalog.locator("[data-chat-row]")).toHaveCount(0);
      await expect(catalog.getByRole("status")).toBeVisible();
      expect(await catalog.getByRole("heading", { level: 1 }).boundingBox()).toEqual(heading);
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    });

    test("service settings expose loading and usable content in the current categories", async ({ page }) => {
      for (const section of ["runtime", "models", "approval"]) {
        const extra = `&section=${section}`;
        await page.goto(fixture("settings", "loaded", extra));
        const target = page.locator(`[data-settings-section="${section}"]`);
        await expect(target).toBeVisible();
        await expect(target.locator("section").first()).toBeVisible();
        await expect(status(page)).toHaveCount(0);
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), section).toBe(false);
        await page.goto(fixture("settings", "loading", extra));
        await accessibleSkeleton(page);
        await expect(target.locator(".animate-pulse > *").first()).toBeVisible();
        await expect(target.getByRole("textbox")).toHaveCount(0);
        await expect(target.getByRole("switch")).toHaveCount(0);
      }
    });

    test("notification preferences remain available when service settings fail", async ({ page }) => {
      for (const state of ["loaded", "loading", "error"]) {
        await page.goto(fixture("settings", state, "&section=notifications&notificationPermission=granted"));
        const target = page.locator('[data-settings-section="notifications"]');
        await expect(target.getByRole("switch")).toHaveCount(5);
        await expect(target.getByRole("switch").nth(1)).toBeEnabled();
        await expect(status(page)).toHaveCount(0);
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
      }
    });

    test("reading preferences stay usable while service settings load or fail", async ({ page }) => {
      await page.goto(fixture("settings", "loaded", "&section=reading&readingSize=24"));
      const target = page.locator('[data-settings-section="reading"]');
      const ready = async () => {
        await expect(target.locator("[data-reading-preview-content] strong")).toBeVisible();
        await expect(target.locator("[data-reading-preview-content] .markdown-content p").first()).toHaveCSS("font-size", "24px");
        await settle(page);
      };
      await ready();
      const layout = ".appearance-theme-grid, .appearance-reading-card, .appearance-size-options, .settings-row";
      const loaded = await boxes(target.locator(layout));
      for (const state of ["loading", "error", "refresh"]) {
        await page.goto(fixture("settings", state, "&section=reading&readingSize=24"));
        await ready();
        sameBoxes(await boxes(target.locator(layout)), loaded, `appearance ${state}`);
        await expect(status(page)).toHaveCount(0);
        const input = target.getByRole("spinbutton");
        await expect(input).toBeEnabled();
        await expect(input).toHaveValue("24");
        await input.fill("22");
        await input.press("Enter");
        await expect(target.locator("[data-reading-preview-content] .markdown-content p").first()).toHaveCSS("font-size", "22px");
        await expect.poll(() => readPreviewPreferences(page).then(values => values.customReadingTextSize)).toBe(22);
        await input.fill("24");
        await input.press("Enter");
      }
    });

    test("calendar and task loading retains navigation, dates and accessible status", async ({ page }) => {
      await page.goto(fixture("automations", "loading"));
      await settle(page);
      await accessibleSkeleton(page);
      await expect(page.getByRole("tab", { name: locale === "en" ? "Calendar" : "日历", exact: true })).toHaveAttribute("aria-selected", "true");
      const days = page.locator(".automation-calendar-days>li");
      await expect(days).toHaveCount(35);
      await page.getByRole("button", { name: locale === "en" ? "Next month" : "下个月" }).click();
      await expect(days).toHaveCount(42);
      if (width === 1440) await expect(days.last()).toBeVisible();
      await page.getByRole("tab", { name: locale === "en" ? "Tasks" : "任务", exact: true }).click();
      await expect(page.locator("[data-automation-task-skeleton]")).toHaveCount(3);
      await accessibleSkeleton(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });

    test("skill detail retains its summary while instructions load", async ({ page }) => {
      const open = async (state: string) => {
        await page.goto(fixture("skill-detail", state));
        await page.getByRole("button", { name: locale === "en" ? "Open details for project-review" : "查看 project-review 详情" }).click();
      };
      await open("loaded");
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByRole("switch")).toBeEnabled();
      await dialog.getByRole("button", { name: locale === "en" ? "Skill instructions" : "技能说明" }).click();
      await expect(dialog.locator("pre")).toContainText("Read the repository instructions before reviewing changes.");
      await open("loading");
      await expect(dialog.getByText("Review the repository and summarize actionable changes.")).toBeVisible();
      await expect(dialog.getByRole("heading", { name: "project-review" })).toBeVisible();
      await expect(dialog.getByRole("switch")).toHaveCount(0);
      await accessibleSkeleton(page);
      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
    });

    test("session automation loading has no stale task actions", async ({ page }) => {
      const open = async (state: string) => {
        await page.goto(fixture("session-jobs", state));
        await page.getByRole("button", { name: locale === "en" ? "Session details" : "会话详情" }).click();
      };
      await open("loaded");
      const dialog = page.getByRole("dialog");
      await expect(dialog.locator('button[aria-haspopup="dialog"]')).toHaveCount(3);
      await open("loading");
      await expect(dialog.locator('button[aria-haspopup="dialog"]')).toHaveCount(0);
      await accessibleSkeleton(page);
      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
    });

    test("cached settings and lists stay visible during background refresh", async ({ page }) => {
      for (const surface of ["settings", "chats", "automations", "session-jobs"]) {
        await page.goto(fixture(surface, "refresh"));
        if (surface === "session-jobs") await page.getByRole("button", { name: locale === "en" ? "Session details" : "会话详情" }).click();
        await settle(page);
        await expect(status(page)).toHaveCount(0);
        await expect(surface === "settings" ? page.getByRole("switch").first() : page.getByText("Project summary", { exact: true }).first()).toBeVisible();
      }
    });
  });
}
