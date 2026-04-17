/**
 * LoginScreen — email/password login + biometric unlock button (S16-002).
 *
 * Shows "Use Face ID" / "Use Touch ID" button when:
 *   - A stored refresh token exists in Keychain
 *   - The device supports biometric authentication
 *
 * Accessibility: all fields labeled, errors announced, focus order sequential.
 */

import React, {useState} from 'react';
import {
  AccessibilityInfo,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {useAuth} from '../contexts/AuthContext';
import {ApiError} from '../api/ApiClient';
import {Colors, Radius, Typography, sp} from '../design-system/tokens';

export function LoginScreen() {
  const {login, unlockBiometric, biometricAvailable, biometricType} =
    useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async () => {
    if (!email.trim() || !password) {
      setError('Email and password are required.');
      AccessibilityInfo.announceForAccessibility(
        'Email and password are required.',
      );
      return;
    }

    setError(null);
    setIsLoading(true);

    try {
      await login(email.trim(), password);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : 'Something went wrong. Please try again.';
      setError(msg);
      AccessibilityInfo.announceForAccessibility(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleBiometric = async () => {
    setError(null);
    setIsLoading(true);
    try {
      await unlockBiometric();
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : 'Biometric unlock failed. Please sign in with your password.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const biometricLabel =
    biometricType === 'FaceID'
      ? 'Use Face ID'
      : biometricType === 'TouchID'
      ? 'Use Touch ID'
      : biometricType === 'Fingerprint'
      ? 'Use Fingerprint'
      : 'Use Biometric';

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <View style={styles.card}>
        <Text style={styles.title} accessibilityRole="header">
          EkamCore
        </Text>
        <Text style={styles.subtitle}>Your local life assistant</Text>

        {error && (
          <View
            style={styles.errorBox}
            accessibilityRole="alert"
            accessibilityLabel={error}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        <View style={styles.field}>
          <Text style={styles.label}>Email</Text>
          <TextInput
            style={[styles.input, error ? styles.inputError : null]}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            autoComplete="email"
            textContentType="emailAddress"
            returnKeyType="next"
            editable={!isLoading}
            accessibilityLabel="Email"
          />
        </View>

        <View style={styles.field}>
          <Text style={styles.label}>Password</Text>
          <TextInput
            style={[styles.input, error ? styles.inputError : null]}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="password"
            textContentType="password"
            returnKeyType="done"
            onSubmitEditing={handleLogin}
            editable={!isLoading}
            accessibilityLabel="Password"
          />
        </View>

        <TouchableOpacity
          style={[styles.button, isLoading && styles.buttonDisabled]}
          onPress={handleLogin}
          disabled={isLoading}
          accessibilityRole="button"
          accessibilityLabel="Sign in"
          accessibilityState={{disabled: isLoading}}>
          {isLoading ? (
            <ActivityIndicator color={Colors.white} />
          ) : (
            <Text style={styles.buttonText}>Sign in</Text>
          )}
        </TouchableOpacity>

        {biometricAvailable && (
          <>
            <View style={styles.divider}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>or</Text>
              <View style={styles.dividerLine} />
            </View>

            <TouchableOpacity
              style={[
                styles.biometricButton,
                isLoading && styles.buttonDisabled,
              ]}
              onPress={handleBiometric}
              disabled={isLoading}
              accessibilityRole="button"
              accessibilityLabel={biometricLabel}
              accessibilityState={{disabled: isLoading}}>
              <Text style={styles.biometricButtonText}>{biometricLabel}</Text>
            </TouchableOpacity>
          </>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: Colors.neutral100,
    justifyContent: 'center',
    padding: sp(4),
  },
  card: {
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: sp(6),
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
  },
  title: {
    ...Typography.display,
    color: Colors.primary,
    textAlign: 'center',
    marginBottom: sp(1),
  },
  subtitle: {
    ...Typography.body,
    color: Colors.neutral600,
    textAlign: 'center',
    marginBottom: sp(6),
  },
  errorBox: {
    backgroundColor: Colors.errorSurface,
    borderRadius: Radius.md,
    padding: sp(3),
    marginBottom: sp(4),
  },
  errorText: {
    ...Typography.small,
    color: Colors.error,
  },
  field: {
    marginBottom: sp(4),
  },
  label: {
    ...Typography.small,
    color: Colors.neutral700,
    marginBottom: sp(1),
    fontWeight: '500',
  },
  input: {
    height: 40,
    borderWidth: 1,
    borderColor: Colors.neutral200,
    borderRadius: Radius.md,
    paddingHorizontal: sp(3),
    ...Typography.body,
    color: Colors.neutral900,
    backgroundColor: Colors.white,
  },
  inputError: {
    borderColor: Colors.error,
    backgroundColor: Colors.errorSurface,
  },
  button: {
    height: 48,
    backgroundColor: Colors.primary,
    borderRadius: Radius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: sp(2),
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    ...Typography.body,
    color: Colors.white,
    fontWeight: '600',
  },
  divider: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: sp(4),
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: Colors.neutral200,
  },
  dividerText: {
    ...Typography.small,
    color: Colors.neutral400,
    marginHorizontal: sp(3),
  },
  biometricButton: {
    height: 48,
    backgroundColor: Colors.white,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  biometricButtonText: {
    ...Typography.body,
    color: Colors.primary,
    fontWeight: '600',
  },
});
