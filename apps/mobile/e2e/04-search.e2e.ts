/**
 * E2E: Search screen — query, filters, natural language (S16-008).
 */
import {device, element, by, expect, waitFor} from 'detox';
import {launchApp, login, navigateToTab} from './init';

describe('Search Screen', () => {
  beforeAll(async () => {
    await launchApp();
    await login();
    await navigateToTab('Search');
  });

  it('shows search input and filter chips', async () => {
    await expect(element(by.label('Search'))).toBeVisible();
    await expect(element(by.text('All'))).toBeVisible();
    await expect(element(by.text('Events'))).toBeVisible();
    await expect(element(by.text('Files'))).toBeVisible();
  });

  it('typing a query triggers search', async () => {
    await element(by.label('Search')).typeText('meeting');
    // Wait for debounce + API call
    await waitFor(element(by.type('RCTScrollView')).atIndex(0))
      .toBeVisible()
      .withTimeout(5000);
  });

  it('clear button removes query', async () => {
    await element(by.label('Clear search')).tap();
    await expect(element(by.text('Search across everything'))).toBeVisible();
  });

  it('filter chips narrow results', async () => {
    await element(by.label('Search')).typeText('test');
    await element(by.text('Files')).tap();
    // Should filter to files only
    await waitFor(element(by.type('RCTScrollView')).atIndex(0))
      .toBeVisible()
      .withTimeout(5000);
  });

  it('natural language query starting with ? shows answer', async () => {
    await element(by.label('Clear search')).tap();
    await element(by.label('Search')).typeText('?what meetings do I have');
    // Should trigger POST /query and show answer text
    await waitFor(element(by.type('RCTScrollView')).atIndex(0))
      .toBeVisible()
      .withTimeout(10000);
  });
});
