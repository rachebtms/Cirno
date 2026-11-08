import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) test(`Router naming keeps a failed draft and saves at ${width}px`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 960 });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const requests: unknown[] = [];
  await page.route("**/v0/auth/status", route => route.fulfill({ json: {
    enabled: true, authenticated: true, registration_required: false, username: "owner", router_handle: "cirno", router_id: "handle_9daf584999d74888c635d1df82976250",
  } }));
  await page.route("**/v0/auth/change-router-name", async route => {
    requests.push(route.request().postDataJSON());
    await route.fulfill(requests.length === 1 ? { status: 409, json: { error: "router_handle_taken" } }
      : { json: { id: "handle_9daf584999d74888c635d1df82976250", name: "snow_9" } });
  });
  await page.goto(`/browser/fixture.html?case=entry&mode=settings&lang=zh-CN&theme=${width === 390 ? "dark" : "light"}`);
  const input = page.getByRole("textbox", { name: /^Router 的 @名称/ });
  await input.fill("taken_name");
  await page.getByRole("button", { name: "保存名称", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("此名称已被其他会话使用");
  await expect(input).toHaveValue("taken_name");
  await input.fill("@Snow_9");
  await page.getByRole("button", { name: "保存名称", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("名称已更新");
  await expect(input).toHaveValue("snow_9");
  expect(requests).toEqual([{ router_handle: "taken_name" }, { router_handle: "snow_9" }]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath(`router-name-${width}.png`), animations: "disabled", fullPage: true });
  expect(errors).toEqual([]);
});
