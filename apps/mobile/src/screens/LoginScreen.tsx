import React, {useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {useAuth} from '../contexts/AuthContext';
import {ApiError} from '../api/client';
import {Colors, Radius, Typography, sp} from '../design-system/tokens';

export function LoginScreen() {
  const {login} = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async () => {
    if (!email.trim() || !password) {
      setError('Email and password are required.');
      return;
    }

    setError(null);
    setIsLoading(true);

    try {
      await login(email.trim(), password);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.message);
      } else {
        setError('Something went wrong. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

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
});
