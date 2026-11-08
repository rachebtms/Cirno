import type { Page } from "@playwright/test";

/** Click and measure HeroUI's visible label; retain its input for state/focus checks. */
export function radioControl(page: Page, name: string) {
  return page.locator('[data-slot="radio"]').filter({
    has: page.getByRole("radio", { name, exact: true }),
  }).locator('[data-slot="radio-content"]');
}

/** Switch inputs retain accessibility state; pointer actions use their visible label. */
export function switchControl(page: Page, name: string) {
  return page.locator('[data-slot="switch"]').filter({
    has: page.getByRole("switch", { name, exact: true }),
  }).locator('[data-slot="switch-content"]');
}
