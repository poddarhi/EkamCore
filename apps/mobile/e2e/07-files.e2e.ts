/**
 * E2E: Files screen — list, type filtering (S16-008).
 */
import {device, element, by, expect, waitFor} from 'detox';
import {launchApp, login, navigateToTab} from './init';

describe('Files Screen', () => {
  beforeAll(async () => {
    await launchApp();
    await login();
  });

  it('search with files filter shows file results', async () => {
    await navigateToTab('Search');
    await element(by.label('Search')).typeText('document');
    await element(by.text('Files')).tap();
    await waitFor(element(by.type('RCTScrollView')).atIndex(0))
      .toBeVisible()
      .withTimeout(5000);
  });
});
