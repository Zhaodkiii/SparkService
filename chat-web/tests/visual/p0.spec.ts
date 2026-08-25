import { test, expect } from "@playwright/test";

test("P0 fixture gallery is available only in fixture mode", async ({ page }) => {
  await page.goto("/p0-fixtures/chat");
  await expect(page.getByRole("heading", { name: "P0 状态画廊" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "输入消息" }).first()).toBeVisible();
});
