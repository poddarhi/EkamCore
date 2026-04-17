/**
 * Detox E2E test initialization (S16-008).
 *
 * Helper functions shared across all E2E specs.
 */

import {device, element, by, expect, waitFor} from 'detox';

export const TEST_EMAIL = 'admin@ekamcore.dev';
export const TEST_PASSWORD = 'admin123';

/** Launch app fresh (clear state). */
export async function launchApp() {
  await device.launchApp({newInstance: true, delete: true});
}

/** Launch app preserving state (for relaunch tests). */
export async function relaunchApp() {
  await device.launchApp({newInstance: true});
}

/** Login with test credentials. */
export async function login() {
  await waitFor(element(by.label('Email')))
    .toBeVisible()
    .withTimeout(10000);

  await element(by.label('Email')).typeText(TEST_EMAIL);
  await element(by.label('Password')).typeText(TEST_PASSWORD);
  await element(by.label('Sign in')).tap();

  // Wait for Today screen to appear
  await waitFor(element(by.text('Today')))
    .toBeVisible()
    .withTimeout(15000);
}

/** Navigate to a specific tab. */
export async function navigateToTab(tab: 'Today' | 'Recap' | 'Search' | 'People' | 'Settings') {
  await element(by.label(tab)).tap();
  await waitFor(element(by.text(tab)))
    .toBeVisible()
    .withTimeout(5000);
}

/** Pull to refresh on the current screen. */
export async function pullToRefresh() {
  await element(by.type('RCTScrollView')).swipe('down', 'slow', 0.5);
}

/** Verify an element is visible within timeout. */
export async function expectVisible(label: string, timeoutMs = 5000) {
  await waitFor(element(by.label(label)))
    .toBeVisible()
    .withTimeout(timeoutMs);
}

/** Verify an element with text is visible. */
export async function expectText(text: string, timeoutMs = 5000) {
  await waitFor(element(by.text(text)))
    .toBeVisible()
    .withTimeout(timeoutMs);
}
