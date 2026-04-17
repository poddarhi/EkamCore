import React from 'react';
import {render, fireEvent, waitFor, screen} from '@testing-library/react-native';
import {LoginScreen} from '../screens/LoginScreen';
import {AuthContext} from '../contexts/AuthContext';

// Minimal AuthContext value for tests (S16-002: added biometric fields)
function makeAuthCtx(overrides: Partial<{
  login: jest.Mock;
  isAuthenticated: boolean;
  isLoading: boolean;
  biometricAvailable: boolean;
}> = {}) {
  return {
    user: null,
    isAuthenticated: false,
    isLoading: false,
    biometricType: null as never,
    biometricAvailable: false,
    login: jest.fn(),
    logout: jest.fn(),
    unlockBiometric: jest.fn(),
    ...overrides,
  };
}

// We need to export AuthContext from AuthContext.tsx — add a named export test wrapper
function renderWithAuth(loginFn: jest.Mock) {
  return render(
    <AuthContext.Provider value={makeAuthCtx({login: loginFn})}>
      <LoginScreen />
    </AuthContext.Provider>,
  );
}

describe('LoginScreen', () => {
  it('renders email + password fields and sign-in button', () => {
    renderWithAuth(jest.fn());

    expect(screen.getByAccessibilityLabel('Email')).toBeTruthy();
    expect(screen.getByAccessibilityLabel('Password')).toBeTruthy();
    expect(screen.getByAccessibilityLabel('Sign in')).toBeTruthy();
  });

  it('shows validation error when fields are empty', async () => {
    renderWithAuth(jest.fn());

    fireEvent.press(screen.getByAccessibilityLabel('Sign in'));

    await waitFor(() => {
      expect(
        screen.getByText('Email and password are required.'),
      ).toBeTruthy();
    });
  });

  it('calls login with trimmed email and password', async () => {
    const loginFn = jest.fn().mockResolvedValue(undefined);
    renderWithAuth(loginFn);

    fireEvent.changeText(screen.getByAccessibilityLabel('Email'), '  user@example.com  ');
    fireEvent.changeText(screen.getByAccessibilityLabel('Password'), 'secret');
    fireEvent.press(screen.getByAccessibilityLabel('Sign in'));

    await waitFor(() => {
      expect(loginFn).toHaveBeenCalledWith('user@example.com', 'secret');
    });
  });

  it('shows API error message on login failure', async () => {
    const {ApiError} = require('../api/client');
    const loginFn = jest
      .fn()
      .mockRejectedValue(
        new ApiError(401, 'AUTH_INVALID_CREDENTIALS', 'Invalid email or password.'),
      );
    renderWithAuth(loginFn);

    fireEvent.changeText(screen.getByAccessibilityLabel('Email'), 'bad@example.com');
    fireEvent.changeText(screen.getByAccessibilityLabel('Password'), 'wrong');
    fireEvent.press(screen.getByAccessibilityLabel('Sign in'));

    await waitFor(() => {
      expect(screen.getByText('Invalid email or password.')).toBeTruthy();
    });
  });
});
