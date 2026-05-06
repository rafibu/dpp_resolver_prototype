import { test, expect } from '@playwright/test';

test.describe('DPP Resolver Smoke Test', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:4200');
  });

  test('should load the federation map', async ({ page }) => {
    await expect(page.locator('app-federation-map')).toBeVisible();
    await expect(page.locator('ngx-graph')).toBeVisible();
  });

  test('should show platforms in sidebar', async ({ page }) => {
    await expect(page.locator('app-sidebar')).toBeVisible();
    // Assuming default platforms are loaded
    await expect(page.locator('.platform-item')).getByText('platform-a').toBeVisible();
  });

  test('should navigate to platform detail', async ({ page }) => {
    await page.click('.platform-item:has-text("platform-a")');
    await expect(page).toHaveURL(/.*platforms\/platform-a/);
    await expect(page.locator('.tab-link.active')).toContainText('DPPs');
  });

  test('should open create DPP modal', async ({ page }) => {
    await page.goto('http://localhost:4200/platforms/platform-a/dpps');
    await page.click('button:has-text("Create DPP")');
    await expect(page.locator('app-create-dpp-modal .modal-container')).toBeVisible();
  });

  test('should navigate to scenario runner', async ({ page }) => {
    await page.click('a:has-text("Scenario Runner")');
    await expect(page).toHaveURL(/.*scenarios/);
    await expect(page.locator('h3:has-text("S1")')).toBeVisible();
  });
});
