import { updatePreviewPreferences } from "./preference-driver";
import { expect, test, type Page } from "@playwright/test";

async function samplePhases(page: Page) {
  return page.getByRole("img", { name: "Agent running", exact: true }).evaluateAll((nodes) => nodes.map((node) => {
    const animation = node.getAnimations({ subtree: true })[0];
    const duration = animation.effect!.getTiming().duration as number;
    return (Number(animation.currentTime) % duration) / duration;
  }));
}

test("catalog activity stays in phase across staggered starts, selection and remounts", async ({ page }) => {
  await page.goto("/browser/fixture.html?case=catalog-activity");
  await expect(page.getByRole("img", { name: "Agent running", exact: true })).toHaveCount(1);
  for (let count = 2; count <= 4; count++) {
    // Stagger arrivals on the actual animation clock, rather than mounting every row together.
    const previous = (await samplePhases(page))[0];
    await expect.poll(async () => Math.abs((await samplePhases(page))[0] - previous)).toBeGreaterThan(0.15);
    await page.getByRole("button", { name: "Start next conversation" }).click();
    await expect(page.getByRole("img", { name: "Agent running", exact: true })).toHaveCount(count);
  }
  const samples = await page.evaluate(() => new Promise<number[][]>((resolve) => {
    const result: number[][] = [];
    const start = performance.now();
    const sample = () => {
      result.push(Array.from(document.querySelectorAll('[role="img"][aria-label="Agent running"]')).map((node) => {
        const animation = node.getAnimations({ subtree: true })[0];
        return (Number(animation.currentTime) % Number(animation.effect!.getTiming().duration)) / Number(animation.effect!.getTiming().duration);
      }));
      if (performance.now() - start < 1500) requestAnimationFrame(sample);
      else resolve(result);
    };
    requestAnimationFrame(sample);
  }));
  expect(samples.length).toBeGreaterThan(10);
  expect(new Set(samples.map((sample) => sample[0].toFixed(2))).size).toBeGreaterThan(10);
  for (const phases of samples) expect(Math.max(...phases) - Math.min(...phases)).toBeLessThan(0.001);

  await page.getByRole("button", { name: "Locate messages", exact: true }).click();
  await page.getByRole("button", { name: "Toggle catalog" }).click();
  await expect(page.getByRole("img", { name: "Agent running", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Toggle catalog" }).click();
  await expect(page.getByRole("img", { name: "Agent running", exact: true })).toHaveCount(4);
  const phases = await samplePhases(page);
  expect(Math.max(...phases) - Math.min(...phases)).toBeLessThan(0.001);
});

test("desktop conversation actions remain visible and keyboard accessible", async ({ page }) => {
  await page.goto("/browser/fixture.html?case=catalog-activity&all");
  const actions = page.getByRole("button", { name: "Conversation actions for Review history", exact: true });
  await expect(actions).toHaveCSS("opacity", "1");
  await page.getByRole("button", { name: "Review history", exact: true }).hover();
  await expect(actions).toHaveCSS("opacity", "1");
  await page.keyboard.press("Tab");
  await actions.focus();
  await expect(actions).toBeFocused();
  await expect(actions).toHaveCSS("opacity", "1");
  await actions.click();
  await expect(page.getByRole("menuitem", { name: "Rename", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(actions).toBeFocused();
  await page.screenshot({ path: test.info().outputPath("desktop-conversation-catalog.png") });
});

test.describe("touch catalog", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

  test("keeps actions visible with touch targets after changing the active conversation", async ({ page }) => {
    await page.goto("/browser/fixture.html?case=catalog-activity&all");
    const actions = page.getByRole("button", { name: "Conversation actions for Review history", exact: true });
    await expect(actions).toHaveCSS("opacity", "1");
    const bounds = await actions.boundingBox();
    expect(bounds!.width).toBeGreaterThanOrEqual(44);
    expect(bounds!.height).toBeGreaterThanOrEqual(44);
    const title = page.getByRole("button", { name: "Review history", exact: true });
    expect((await title.boundingBox())!.width).toBeGreaterThan(200);
    await expect(page.getByRole("combobox", { name: "Move Review history to project", exact: true })).toHaveCount(0);
    await actions.tap();
    await page.getByRole("menuitem", { name: "Projects", exact: true }).tap();
    await expect(page.getByRole("menuitemradio", { name: "Unfiled conversations", exact: true })).toHaveAttribute("aria-checked", "true");
    await page.getByRole("menuitemradio", { name: "Unfiled conversations", exact: true }).tap();
    await expect(page.getByRole("menu", { name: "Conversation actions for Review history", exact: true })).toBeHidden();
    await page.getByRole("button", { name: "Locate messages", exact: true }).tap();
    await expect(actions).toHaveCSS("opacity", "1");
    await page.getByRole("button", { name: "Conversation actions for Locate messages", exact: true }).tap();
    await page.getByRole("menuitem", { name: "Rename", exact: true }).tap();
    const input = page.getByRole("textbox", { name: "Conversation name" });
    await expect(input).toBeVisible();
    await expect(input).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath("mobile-conversation-catalog.png") });
  });
});

for (const width of [1280, 390]) {
  test(`catalog Ring follows the neutral theme at ${width}px and respects live motion preferences`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/browser/fixture.html?case=catalog-activity&all");
    const indicators = page.getByRole("img", { name: "Agent running", exact: true });
    await expect(indicators).toHaveCount(4);
    const colors: string[] = [];
    for (const dark of [false, true]) {
      await updatePreviewPreferences(page, { themeMode: dark ? "dark" : "light" });
      const actual = await indicators.evaluateAll((nodes) => nodes.map((node) => {
        const svg = node.querySelector("svg")!;
        const reference = document.createElement("span");
        reference.style.color = "var(--muted)";
        node.append(reference);
        const expectedColor = getComputedStyle(reference).color;
        reference.remove();
        const rect = svg.getBoundingClientRect();
        return { color: getComputedStyle(svg).color, expectedColor, size: [rect.width, rect.height] };
      }));
      for (const item of actual) {
        expect(item.color).toBe(item.expectedColor);
        expect(item.size[0]).toBeGreaterThanOrEqual(15);
        expect(item.size[0]).toBeLessThanOrEqual(20);
        expect(item.size[1]).toBe(item.size[0]);
      }
      colors.push(actual[0].color);
      await page.getByRole("button", { name: "Locate messages", exact: true }).hover();
      await page.getByRole("button", { name: "Refine message bubbles", exact: true }).click();
      expect(await indicators.evaluateAll((nodes) => nodes.map((node) => getComputedStyle(node.querySelector("svg")!).color)))
        .toEqual(Array(4).fill(actual[0].color));
    }
    expect(colors[0]).not.toBe(colors[1]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

    for (const reducedMotion of ["reduce", "no-preference"] as const) {
      await page.emulateMedia({ reducedMotion });
      await expect.poll(() => indicators.evaluateAll((nodes) => nodes.map((node) => node.getAnimations({ subtree: true }).length)))
        .toEqual(Array(4).fill(reducedMotion === "reduce" ? 0 : 1));
      if (reducedMotion === "no-preference") {
        const phases = await samplePhases(page);
        expect(Math.max(...phases) - Math.min(...phases)).toBeLessThan(0.001);
      }
    }
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.getByRole("button", { name: "Reset conversations" }).click();
    await page.getByRole("button", { name: "Start next conversation" }).click();
    await expect(indicators).toHaveCount(2);
    expect(await indicators.evaluateAll((nodes) => nodes.map((node) => node.getAnimations({ subtree: true }).length))).toEqual([0, 0]);
  });
}
