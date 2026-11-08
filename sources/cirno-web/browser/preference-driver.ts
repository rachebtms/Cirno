import type { Page } from "@playwright/test";
import type { OwnerPreferences } from "@/features/preferences/contracts";

// Component fixtures use a shared simulated server, independent of product storage.
const key = "cirno-browser-fixture.owner-preferences";

export async function seedPreviewPreferences(page: Page, values: Partial<OwnerPreferences>) {
  await page.addInitScript(({ key, values }) => {
    if (!localStorage.getItem(key)) {
      localStorage.setItem(key, JSON.stringify({ revision: 0, values }));
    }
  }, { key, values });
}

export async function readPreviewPreferences(page: Page): Promise<OwnerPreferences> {
  return page.evaluate(key => JSON.parse(localStorage.getItem(key)!).values, key);
}


/** Deliver a simulated server update through the same preview subscription as another client. */
export async function updatePreviewPreferences(page: Page, values: Partial<OwnerPreferences>) {
  await page.evaluate(({ key, values }) => {
    const previous = JSON.parse(localStorage.getItem(key)!);
    const next = JSON.stringify({ ...previous, revision: previous.revision + 1, values: { ...previous.values, ...values } });
    localStorage.setItem(key, next);
    window.dispatchEvent(new StorageEvent("storage", { key, newValue: next }));
  }, { key, values });
  if (values.themeMode && values.themeMode !== "system") {
    await page.waitForFunction(dark => document.documentElement.classList.contains("dark") === dark, values.themeMode === "dark");
  }
}
