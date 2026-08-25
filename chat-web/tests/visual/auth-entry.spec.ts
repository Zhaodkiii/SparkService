import { expect, test } from "@playwright/test";

test("anonymous visitor is redirected from home to login", async ({ context, page }) => {
  await context.clearCookies();
  await page.goto("/");

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "登录以解锁更多功能" })).toBeVisible();
});
