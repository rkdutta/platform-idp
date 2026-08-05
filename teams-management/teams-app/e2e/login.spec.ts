import { test, expect } from '@playwright/test';

// Real login against the live Keycloak `teams` realm — no mocking. Demo
// credentials (see platform-infra/apps/security/keycloak). teams-app has no
// route guard forcing an auto-redirect (AuthGuard exists but isn't wired
// into app-routing.module.ts); login is driven entirely by the "/" page's
// own login prompt button (see app.component.html).

test('unauthenticated visitor sees the login prompt, not the app', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Welcome to Teams Management' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Login with Keycloak' })).toBeVisible();
  // The logged-in-only nav must not be present.
  await expect(page.getByRole('link', { name: 'Projects' })).toHaveCount(0);
});

test('teamlead1 can log in via Keycloak and reach the authenticated portal', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Login with Keycloak' }).click();

  // Keycloak's default theme login form.
  await page.waitForURL(/platform-auth\.127\.0\.0\.1\.sslip\.io/);
  await page.locator('#username').fill('teamlead1');
  await page.locator('#password').fill('password123');
  await page.locator('#kc-login').click();

  // Back on teams-app, now authenticated.
  await page.waitForURL(/teams-ui\.127\.0\.0\.1\.sslip\.io/);
  await expect(page.getByRole('link', { name: 'Projects', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Welcome to Teams Management' })).toHaveCount(0);
});
