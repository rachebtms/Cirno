import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) test(`delivery progress remains at its first position at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/browser/fixture.html?case=message-delivery&locale=en");
  await page.getByRole("button", { name: "Complete delivery", exact: true }).click();
  await expect(page.getByRole("button", { name: "Copy code", exact: true })).toHaveCount(0);
  const worked = page.getByRole("button", { name: /^Worked/ });
  if (await worked.getAttribute("aria-expanded") === "false") await worked.click();
  const sent = page.getByText("Sent message", { exact: true });
  await expect(sent).toHaveCount(1);
  await page.getByRole("button", { name: "Expand step", exact: true }).click();
  await expect(page.getByText("Message sent to websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", { exact: false })).toBeVisible();
  const details = page.getByTestId("activity-step-details");
  await expect.poll(() => details.evaluate(element => {
    const container = element.getBoundingClientRect();
    const range = document.createRange();
    range.selectNodeContents(element);
    const rectangles = Array.from(range.getClientRects());
    return rectangles.every(rectangle => rectangle.right <= container.right + 1 && rectangle.bottom <= container.bottom + 1);
  })).toBe(true);
  await expect(page.getByRole("button", { name: /^Worked/ })).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `/tmp/cirno-review79-delivery-${width}.png`, fullPage: true });
});
