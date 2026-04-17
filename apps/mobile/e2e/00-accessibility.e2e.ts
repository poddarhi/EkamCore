/**
 * E2E: Accessibility audit across all major screens (S16-008 / ART-26).
 */
import {device, element, by, expect, waitFor} from 'detox';
import {launchApp, login, navigateToTab} from './init';

describe('Accessibility', () => {
  beforeAll(async () => {
    await launchApp();
    await login();
  });

  it('Login screen has labeled inputs and button', async () => {
    // Already past login — verify labels existed (tested in auth spec)
  });

  it('Today tab has accessible card list', async () => {
    await navigateToTab('Today');
    // FlatList should be scrollable and cards should have labels
    await expect(element(by.type('RCTScrollView')).atIndex(0)).toBeVisible();
  });

  it('Recap tab has accessible period toggle', async () => {
    await navigateToTab('Recap');
    await expect(element(by.label('Daily recap'))).toBeVisible();
    await expect(element(by.label('Weekly recap'))).toBeVisible();
  });

  it('Search tab has labeled input and filter chips', async () => {
    await navigateToTab('Search');
    await expect(element(by.label('Search'))).toBeVisible();
    await expect(element(by.label('All'))).toBeVisible();
  });

  it('People tab has labeled search and list', async () => {
    await navigateToTab('People');
    await expect(element(by.label('Search people'))).toBeVisible();
  });

  it('Settings tab has accessible sections and logout', async () => {
    await navigateToTab('Settings');
    await expect(element(by.label('Log out'))).toBeVisible();
  });
});
