import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  for (const locale of ["en", "zh-CN"]) {
    test.describe(`Workspace ${width}px ${locale}`, () => {
      test.use({
        viewport: { width, height: width === 390 ? 844 : 960 },
        isMobile: width === 390,
        hasTouch: width === 390,
      });
      test("independent tabs, inline file editor, unsaved close guard and mobile layout", async ({
        page,
      }, info) => {
        const zh = locale === "zh-CN";
        await page.goto(`/browser/fixture.html?case=workspace&lang=${locale}`);
        const launcher = page.getByRole("navigation", {
          name: zh ? "Launcher" : "Launcher",
        });
        await launcher
          .getByRole("button", {
            name: zh ? "打开文件" : "Open Files",
            exact: true,
          })
          .click();
        await page
          .getByRole("button", { name: "notes.md", exact: true })
          .click();
        const editor = page.getByRole("textbox", {
          name: zh ? "文件内容" : "File contents",
        });
        await expect(editor).toBeVisible();
        await editor.fill("# Updated notes\n\nUnsaved research results.");
        const fileTab = page.getByRole("tab", {
          name: "notes.md",
          exact: true,
        });
        await expect(fileTab).toBeVisible();
        await page
          .getByRole("button", {
            name: zh ? "关闭 notes.md" : "Close notes.md",
            exact: true,
          })
          .click();
        await expect(page.getByRole("alertdialog")).toBeVisible();
        await page
          .getByRole("alertdialog")
          .getByRole("button", { name: zh ? "取消" : "Cancel", exact: true })
          .click();
        await expect(editor).toHaveValue(
          "# Updated notes\n\nUnsaved research results.",
        );
        await page
          .getByRole("button", { name: zh ? "保存" : "Save", exact: true })
          .click();
        await expect(
          page.getByRole("button", { name: zh ? "保存" : "Save", exact: true }),
        ).toBeDisabled();
        await page.screenshot({ path: info.outputPath("workspace-file.png") });
        await launcher
          .getByRole("button", {
            name: zh ? "打开@cirno" : "Open @cirno",
            exact: true,
          })
          .click();
        await expect(
          page.getByRole("tab", { name: "@cirno", exact: true }),
        ).toHaveAttribute("aria-selected", "true");
        await expect(fileTab).toHaveAttribute("aria-selected", "false");
        await expect(
          page.getByRole("tabpanel").filter({ visible: true }),
        ).toHaveCount(1);
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth,
          ),
        ).toBe(false);
        await page.screenshot({ path: info.outputPath("workspace-chat.png") });
        await launcher
          .getByRole("button", {
            name: zh ? "打开终端" : "Open Terminal",
            exact: true,
          })
          .click();
        await expect(
          page.getByRole("button", {
            name: zh ? "连接" : "Connect",
            exact: true,
          }),
        ).toBeVisible();
        await page
          .getByRole("button", { name: zh ? "连接" : "Connect", exact: true })
          .click();
        await expect(page.locator(".xterm")).toBeVisible();
        await expect(page.getByRole("alert")).toHaveCount(0);
        await launcher
          .getByRole("button", {
            name: zh ? "打开终端" : "Open Terminal",
            exact: true,
          })
          .click();
        await expect(
          page.getByRole("tab", {
            name: zh ? "终端" : "Terminal",
            exact: true,
          }),
        ).toHaveCount(2);
        await expect(
          page.getByRole("tabpanel").filter({ visible: true }),
        ).toHaveCount(1);
        await page.screenshot({
          path: info.outputPath("workspace-terminal.png"),
        });
      });
      test("trace and credentials fit the viewport", async ({ page }, info) => {
        const zh = locale === "zh-CN";
        await page.goto(`/browser/fixture.html?case=workspace&lang=${locale}`);
        await page.getByRole("navigation", { name: zh ? "Launcher" : "Launcher" })
          .getByRole("button", { name: zh ? "打开轨迹" : "Open Trace", exact: true }).click();
        await page.locator('[data-event-kind="request"]').first().click();
        await expect(
          page.getByText(
            "You are Cirno, the owner's personal research agent.",
            { exact: false },
          ),
        ).toBeVisible();
        await page.screenshot({ path: info.outputPath("workspace-trace.png") });
        await page.getByRole("navigation", { name: zh ? "Launcher" : "Launcher" })
          .getByRole("button", { name: zh ? "打开凭据" : "Open Credentials", exact: true }).click();
        await page
          .getByRole("button", {
            name: zh ? "添加凭据" : "Add record",
            exact: true,
          })
          .click();
        await expect(
          page.getByRole("textbox", {
            name: zh ? /^敏感内容/ : /^Sensitive value/,
          }),
        ).toBeVisible();
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth,
          ),
        ).toBe(false);
        const secret = page.getByRole("textbox", {
          name: zh ? /^敏感内容/ : /^Sensitive value/,
        });
        await secret.fill("Owner's unsaved private note");
        await page
          .getByRole("button", {
            name: zh ? "关闭 凭据" : "Close Credentials",
            exact: true,
          })
          .click();
        await expect(page.getByRole("alertdialog")).toBeVisible();
        await page
          .getByRole("alertdialog")
          .getByRole("button", { name: zh ? "取消" : "Cancel", exact: true })
          .click();
        await expect(secret).toHaveValue("Owner's unsaved private note");
        const launch = page.getByRole("navigation", {
          name: zh ? "Launcher" : "Launcher",
        });
        await launch
          .getByRole("button", {
            name: zh ? "打开@cirno" : "Open @cirno",
            exact: true,
          })
          .click();
        await page
          .getByRole("tab", { name: zh ? "凭据" : "Credentials", exact: true })
          .click();
        await expect(secret).toHaveValue("Owner's unsaved private note");
        await page.screenshot({
          path: info.outputPath("workspace-credentials.png"),
        });
      });
    });
  }
}

for (const width of [390, 1440]) test(`launchers and separate conversation catalogs stay consistent at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/browser/fixture.html?case=workspace&lang=en");
  const launcher = page.getByRole("navigation", { name: "Launcher", exact: true });
  await expect(launcher.getByRole("button")).toHaveCount(12);
  await expect(launcher.getByRole("button", { name: "Open Memory", exact: true })).toHaveCount(1);
  const buttons = launcher.locator("[data-launcher-scroll]").getByRole("button");
  const first = (await buttons.nth(0).boundingBox())!, second = (await buttons.nth(1).boundingBox())!;
  expect(first.width).toBeGreaterThanOrEqual(43);
  expect(width === 390 ? second.x - first.x : second.y - first.y).toBeGreaterThanOrEqual(43);
  await expect(page.getByText("I am checking the experiment results.", { exact: true })).toBeVisible();
  await expect(page.getByText("A background check found one result ready for review.", { exact: true })).toBeVisible();
  await launcher.getByRole("button", { name: "Open Conversations", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Research project", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Research worker", exact: true })).toBeVisible();
  await launcher.getByRole("button", { name: "Open Conversations", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Conversations", exact: true })).toHaveCount(1);
  await expect(page.getByRole("tabpanel").filter({ visible: true })).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("launcher shortcut hints describe the keyboard actions", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/browser/fixture.html?case=workspace&lang=en");
  const create = page.getByRole("navigation", { name: "Launcher", exact: true })
    .getByRole("button", { name: "Open New conversation", exact: true });
  await page.mouse.move(720, 400);
  await create.hover();
  await expect(page.getByRole("tooltip")).toContainText("New conversation");
  await expect(page.getByRole("tooltip").locator("kbd")).toHaveText(/(?:Ctrl\+Shift\+|⌘⇧)O/);
});
