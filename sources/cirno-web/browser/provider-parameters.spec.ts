import { expect, test } from "@playwright/test";

for (const locale of ["en", "zh-CN"]) for (const width of [390, 1280]) {
  test(`request parameter JSON stays editable and validates in ${locale} at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/gallery.html?lang=${locale}#component=sources%2Fcirno-web%2Fsrc%2Ffeatures%2Fsettings%2Fproviders%2FProviderParameterFields.tsx`);
    const preview = page.getByRole("region", { name: locale === "en" ? "Component preview" : "组件预览", exact: true });
    const fields = preview.getByRole("textbox");
    await expect(fields).toHaveCount(3);
    const headers = fields.first();
    await expect(headers).toHaveValue('{"X-Project":"gallery"}');
    await headers.fill("[");
    await expect(headers).toHaveAttribute("aria-invalid", "true");
    await headers.fill('{"X-Project":7}');
    await expect(headers).toHaveAttribute("aria-invalid", "true");
    const draft = JSON.stringify({ "X-Project": "research" }, null, 2);
    await headers.fill(draft);
    await expect(headers).not.toHaveAttribute("aria-invalid", "true");
    await expect.poll(async () => JSON.parse((await preview.getByRole("status").textContent())!).extraHeaders).toBe(draft);
    await expect(headers).toHaveValue(draft);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
