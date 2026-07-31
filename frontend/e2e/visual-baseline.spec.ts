import { expect, test, type Page } from '@playwright/test';

import { installMockMakerApi } from './fixtures/mockMakerApi';

async function openApp(page: Page) {
  await installMockMakerApi(page);
  await page.goto('/chatBot/');
  await expect(page.locator('.app-shell')).not.toHaveAttribute('aria-busy', 'true');
  await expect(page.locator('.msg-row')).toHaveCount(2);
  await page.locator('.chat-scroll').evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
}

test('desktop light rich answer', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await openApp(page);
  await expect(page).toHaveScreenshot('desktop-light-rich-answer.png');
});

test('desktop dark rich answer', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await openApp(page);
  await page.locator('.theme-toggle').click();
  await expect(page.locator('html')).toHaveAttribute('theme-mode', 'dark');
  await expect(page.locator('html')).not.toHaveClass(/theme-transitioning/);
  await expect(page).toHaveScreenshot('desktop-dark-rich-answer.png');
});

test('mobile chat', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openApp(page);
  await expect(page).toHaveScreenshot('mobile-chat.png');
});

test('reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1280, height: 800 });
  await openApp(page);
  await expect(page).toHaveScreenshot('reduced-motion.png');
});

test('Skills marketplace', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await openApp(page);
  await page.locator('[data-onboarding="skills"]').click();
  await expect(page.locator('.skills-page')).toBeVisible();
  await expect(page.locator('.skills-page-card')).toHaveCount(2);
  await expect(page).toHaveScreenshot('skills-marketplace.png');
});
