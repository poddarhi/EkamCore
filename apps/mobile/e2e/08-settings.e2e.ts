/**
 * E2E: Settings screen — sections, cache clear, logout (S16-008).
 */
import {device, element, by, expect, waitFor} from 'detox';
import {launchApp, login, navigateToTab} from './init';

describe('Settings Screen', () => {
  beforeAll(async () => {
    await launchApp();
    await login();
    await navigateToTab('Settings');
  });

  it('renders all settings sections', async () => {
    await expect(element(by.text('Account'))).toBeVisible();
    await expect(element(by.text('Hub Connection'))).toBeVisible();
    await expect(element(by.text('Cache'))).toBeVisible();
    await expect(element(by.text('About'))).toBeVisible();
  });

  it('shows connection status', async () => {
    await expect(element(by.text('Status'))).toBeVisible();
  });

  it('test connection button works', async () => {
    await element(by.text('Test Connection')).tap();
    // Should show Alert (success or failure)
    await waitFor(element(by.text('OK')))
      .toBeVisible()
      .withTimeout(10000);
    await element(by.text('OK')).tap();
  });

  it('clear cache button shows confirmation', async () => {
    await element(by.text('Clear Cache')).tap();
    await waitFor(element(by.text('Clear')))
      .toBeVisible()
      .withTimeout(3000);
    await element(by.text('Cancel')).tap();
  });

  it('logout from settings', async () => {
    await element(by.label('Log out')).tap();
    await waitFor(element(by.text('Log Out')))
      .toBeVisible()
      .withTimeout(3000);
    // Cancel instead of actually logging out (preserve session for other tests)
    await element(by.text('Cancel')).tap();
  });
});
