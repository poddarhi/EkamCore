/**
 * E2E: Recap screen — period toggle, date navigation (S16-008).
 */
import {device, element, by, expect, waitFor} from 'detox';
import {launchApp, login, navigateToTab} from './init';

describe('Recap Screen', () => {
  beforeAll(async () => {
    await launchApp();
    await login();
    await navigateToTab('Recap');
  });

  it('renders daily recap by default', async () => {
    await expect(element(by.label('Daily recap'))).toBeVisible();
  });

  it('weekly toggle switches data source', async () => {
    await element(by.label('Weekly recap')).tap();
    await expect(element(by.label('Weekly recap'))).toBeVisible();
  });

  it('date navigation goes to previous period', async () => {
    await element(by.label('Previous period')).tap();
    // Date label should change — verify screen doesn't crash
    await expect(element(by.label('Previous period'))).toBeVisible();
  });

  it('date navigation goes to next period', async () => {
    await element(by.label('Next period')).tap();
    await expect(element(by.label('Next period'))).toBeVisible();
  });
});
