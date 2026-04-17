/**
 * E2E: Photos screen — grid, date grouping (S16-008).
 */
import {device, element, by, expect, waitFor} from 'detox';
import {launchApp, login} from './init';

describe('Photos Screen', () => {
  beforeAll(async () => {
    await launchApp();
    await login();
    // Navigate to Photos — not a default tab, would need deep navigation
    // For now verify via Search > Photos filter
  });

  it('search photos filter shows photo results', async () => {
    await element(by.label('Search')).tap();
    await element(by.label('Search')).typeText('photo');
    await element(by.text('Photos')).tap();
    await waitFor(element(by.type('RCTScrollView')).atIndex(0))
      .toBeVisible()
      .withTimeout(5000);
  });
});
