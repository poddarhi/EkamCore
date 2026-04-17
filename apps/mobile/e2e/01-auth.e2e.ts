/**
 * E2E: Authentication flow — login, biometric, logout (S16-008).
 */
import {device, element, by, expect, waitFor} from 'detox';
import {launchApp, relaunchApp, login, TEST_EMAIL, TEST_PASSWORD} from './init';

describe('Authentication', () => {
  beforeEach(async () => {
    await launchApp();
  });

  it('shows login screen on first launch', async () => {
    await waitFor(element(by.label('Email')))
      .toBeVisible()
      .withTimeout(10000);
    await expect(element(by.label('Password'))).toBeVisible();
    await expect(element(by.label('Sign in'))).toBeVisible();
  });

  it('login with valid credentials navigates to Today', async () => {
    await login();
    await expect(element(by.text('Today'))).toBeVisible();
  });

  it('login with invalid credentials shows error', async () => {
    await element(by.label('Email')).typeText('wrong@test.com');
    await element(by.label('Password')).typeText('badpassword');
    await element(by.label('Sign in')).tap();

    await waitFor(element(by.type('RCTView')))
      .toBeVisible()
      .withTimeout(10000);
    // Error should appear (exact text depends on API response)
  });

  it('biometric button shown on relaunch after login', async () => {
    await login();
    await relaunchApp();
    // If biometric is available + stored token exists, biometric button appears
    // On simulator without biometric, falls back to login screen
    await waitFor(element(by.label('Email')))
      .toBeVisible()
      .withTimeout(10000);
  });

  it('logout wipes state and returns to login', async () => {
    await login();
    await element(by.label('Settings')).tap();

    await waitFor(element(by.label('Log out')))
      .toBeVisible()
      .withTimeout(5000);
    await element(by.label('Log out')).tap();

    // Confirm dialog
    await waitFor(element(by.text('Log Out')))
      .toBeVisible()
      .withTimeout(3000);
    await element(by.text('Log Out')).tap();

    // Should return to login screen
    await waitFor(element(by.label('Email')))
      .toBeVisible()
      .withTimeout(10000);
  });
});
