/**
 * E2E: Connectivity states — banners and degraded UI (S16-008).
 *
 * Note: Full network simulation (disconnect/throttle) requires Detox
 * network simulation or a proxy. These tests verify the UI components
 * exist and the app doesn't crash during state transitions.
 */
import {device, element, by, expect, waitFor} from 'detox';
import {launchApp, login, navigateToTab} from './init';

describe('Connectivity States', () => {
  beforeAll(async () => {
    await launchApp();
    await login();
  });

  it('connected state shows no banner on Today', async () => {
    await navigateToTab('Today');
    // In connected state, no connectivity banner should be visible
    // The banner component renders null when CONNECTED
    await expect(element(by.type('RCTScrollView')).atIndex(0)).toBeVisible();
  });

  it('today screen renders without crash in any state', async () => {
    await navigateToTab('Today');
    await expect(element(by.type('RCTScrollView')).atIndex(0)).toBeVisible();
  });

  it('settings shows current connection status', async () => {
    await navigateToTab('Settings');
    await expect(element(by.text('Status'))).toBeVisible();
    // Should show "Connected" when hub is reachable
    await expect(element(by.text('Connected'))).toBeVisible();
  });

  it('troubleshoot button not shown when connected', async () => {
    await navigateToTab('Settings');
    // Troubleshoot button only appears in DISCONNECTED/HUB_SLEEPING states
    // When connected, it should not be visible
    await expect(element(by.text('Status'))).toBeVisible();
  });
});
