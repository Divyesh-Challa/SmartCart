import { expect, test } from "@playwright/test";
import { setLocation, signIn } from "./session";

const shots = (name: string) => ({ path: `e2e-screenshots/${name}.png`, fullPage: true });

test("home sets a location and shows real store coverage", async ({ page }) => {
  await setLocation(page);
  await expect(page.getByText(/Edmonton-area stores/)).toBeVisible();
  await page.screenshot(shots("01-home"));
});

test("signed-out visitors are asked to sign in before adding prices", async ({ page }) => {
  await page.goto("/add-price");
  await expect(page.getByText("Sign in to add prices.")).toBeVisible();
});

test("a shopper adds a price, sees it in Compare, and gets a trip plan", async ({ page }) => {
  await signIn(page, "shopper@example.com");
  await setLocation(page);

  await page.goto("/add-price");
  await expect(page.getByText("Take or choose a photo")).toBeVisible();
  const store = page.getByLabel("Store");
  await expect(store.locator("option").nth(1)).toBeAttached();
  await store.selectOption({ index: 1 });
  await page.getByLabel("Item", { exact: true }).fill("butter");
  await page.getByRole("option", { name: /Salted Butter/ }).click();
  await page.getByLabel("Price paid ($)").fill("5.49");
  await page.screenshot(shots("02-add-price"));
  await page.getByRole("button", { name: "Submit price" }).click();
  await expect(page.getByText(/Thanks! Your price/)).toBeVisible();

  await page.goto("/compare");
  await page.getByPlaceholder("Search an item, e.g. butter").fill("butter");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText("$5.49").first()).toBeVisible();
  await page.screenshot(shots("03-compare"));

  await page.goto("/list");
  await page.getByPlaceholder("Item, e.g. eggs").fill("salted butter");
  const saved = page.waitForResponse((r) => r.url().endsWith("/api/me/list") && r.request().method() === "PUT");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  expect((await saved).ok()).toBe(true);
  await expect(page.getByText("Saved to your account.")).toBeVisible();
  // The list is on the account, so it survives clearing this device.
  await page.evaluate(() => localStorage.removeItem("sc.list.v1"));
  await page.reload();
  await expect(page.getByText("salted butter", { exact: true })).toBeVisible();
  await page.screenshot(shots("04-list"));
  await page.getByRole("link", { name: "Find the cheapest trip" }).click();
  await expect(page.getByText("$5.49").first()).toBeVisible();
  // One store with one price: all three plans match, so they're shown as one card.
  await expect(page.getByRole("heading", { level: 2 })).toHaveCount(1);
  await page.screenshot(shots("05-plan"));
});

test("the owner adds a flyer from the admin screen", async ({ page }) => {
  await signIn(page, "admin@example.com");
  await page.goto("/account");
  await page.getByRole("link", { name: "Open admin tools" }).click();
  await expect(page.getByRole("heading", { name: "Add a flyer" })).toBeVisible();
  const chain = page.getByLabel("Store chain");
  await expect(chain.locator("option").nth(1)).toBeAttached();
  await chain.selectOption("No Frills");
  await page.getByLabel("Flyer title").fill("Weekly flyer");
  await page.getByLabel(/Deals \(one per line/).fill("Salted Butter 454g | Dairy | 4.99 | 6.99");
  await page.getByRole("button", { name: "Save flyer" }).click();
  await expect(page.getByText("Flyer saved with 1 deal.")).toBeVisible();
  // Starts today (local calendar), so it's listed straight away.
  await expect(page.getByText(/No Frills: Weekly flyer/)).toBeVisible();
  await page.screenshot(shots("06-admin"));
});

test("legal pages render", async ({ page }) => {
  await page.goto("/legal/privacy");
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  await page.screenshot(shots("07-privacy"));
});
