import { defineConfig, devices } from '@playwright/test';

// e2e against the LIVE deployed teams-app (not a locally-served build) — set
// TEAMS_APP_URL to override. Self-signed platform-tls cert, hence
// ignoreHTTPSErrors. No webServer block: this is a smoke test against
// whatever's actually running in the cluster, not a build-and-serve test.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: true,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: process.env['TEAMS_APP_URL'] || 'https://teams-ui.127.0.0.1.sslip.io:8443',
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
