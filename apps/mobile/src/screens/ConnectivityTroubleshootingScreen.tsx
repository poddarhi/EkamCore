/**
 * ConnectivityTroubleshootingScreen — step-by-step diagnostics (S16-007).
 */

import React, {useCallback, useEffect, useState} from 'react';
import {
  Linking,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {apiClient} from '../api/ApiClient';
import {Colors, Radius, Typography, sp} from '../design-system/tokens';

type CheckStatus = 'pending' | 'running' | 'pass' | 'fail';

interface DiagStep {
  id: string;
  label: string;
  status: CheckStatus;
  detail?: string;
}

interface Props {
  onBack?: () => void;
  onLoginAgain?: () => void;
}

export function ConnectivityTroubleshootingScreen({onBack, onLoginAgain}: Props) {
  const [steps, setSteps] = useState<DiagStep[]>([
    {id: 'network', label: 'Checking network connectivity...', status: 'pending'},
    {id: 'tailscale', label: 'Checking Tailscale connection...', status: 'pending'},
    {id: 'hub', label: 'Reaching EkamCore hub...', status: 'pending'},
    {id: 'auth', label: 'Checking authentication...', status: 'pending'},
  ]);
  const [running, setRunning] = useState(false);

  const updateStep = useCallback(
    (id: string, patch: Partial<DiagStep>) => {
      setSteps(prev =>
        prev.map(s => (s.id === id ? {...s, ...patch} : s)),
      );
    },
    [],
  );

  const runDiagnostics = useCallback(async () => {
    setRunning(true);
    // Reset all steps
    setSteps(prev => prev.map(s => ({...s, status: 'pending', detail: undefined})));

    // Step 1: Network (basic fetch test)
    updateStep('network', {status: 'running'});
    try {
      const netCtrl = new AbortController();
      const netTimer = setTimeout(() => netCtrl.abort(), 5000);
      await fetch('https://1.1.1.1', {method: 'HEAD', signal: netCtrl.signal});
      clearTimeout(netTimer);
      updateStep('network', {status: 'pass', detail: 'Internet reachable'});
    } catch {
      updateStep('network', {
        status: 'fail',
        detail: 'No internet connection. Check Wi-Fi or cellular.',
      });
      setRunning(false);
      return;
    }

    // Step 2: Tailscale (try to reach the Tailscale peer)
    updateStep('tailscale', {status: 'running'});
    const hubBase = apiClient.getBaseUrl().replace('/api/v1', '');
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 5000);
      await fetch(hubBase, {method: 'HEAD', signal: ctrl.signal});
      clearTimeout(timer);
      updateStep('tailscale', {status: 'pass', detail: 'Hub address reachable'});
    } catch {
      updateStep('tailscale', {
        status: 'fail',
        detail: 'Cannot reach hub. Is Tailscale connected? Is your Mac awake?',
      });
      setRunning(false);
      return;
    }

    // Step 3: Hub health endpoint
    updateStep('hub', {status: 'running'});
    try {
      await apiClient.request({path: '/health', noRetry: true});
      updateStep('hub', {status: 'pass', detail: 'EkamCore API responding'});
    } catch {
      updateStep('hub', {
        status: 'fail',
        detail: 'Hub is reachable but API is not responding. Docker services may be stopped.',
      });
      setRunning(false);
      return;
    }

    // Step 4: Auth
    updateStep('auth', {status: 'running'});
    try {
      await apiClient.request({path: '/settings', noRetry: true});
      updateStep('auth', {status: 'pass', detail: 'Authenticated'});
    } catch {
      updateStep('auth', {
        status: 'fail',
        detail: 'Session expired. You need to sign in again.',
      });
    }

    setRunning(false);
  }, [updateStep]);

  useEffect(() => {
    runDiagnostics();
  }, [runDiagnostics]);

  const allPassed = steps.every(s => s.status === 'pass');
  const firstFail = steps.find(s => s.status === 'fail');

  const STATUS_ICON: Record<CheckStatus, string> = {
    pending: '\u25CB',
    running: '\u25CC',
    pass: '\u2713',
    fail: '\u2717',
  };

  const STATUS_COLOR: Record<CheckStatus, string> = {
    pending: Colors.neutral400,
    running: Colors.primaryLight,
    pass: Colors.success,
    fail: Colors.error,
  };

  return (
    <SafeAreaView style={styles.root}>
      <ScrollView contentContainerStyle={styles.scroll}>
        {onBack && (
          <TouchableOpacity onPress={onBack} style={styles.backBtn} accessibilityLabel="Back">
            <Text style={styles.backText}>{'<'} Back</Text>
          </TouchableOpacity>
        )}

        <Text style={styles.heading} accessibilityRole="header">
          Connection Troubleshooting
        </Text>
        <Text style={styles.subtitle}>
          Running diagnostics to find the issue...
        </Text>

        {/* Steps */}
        <View style={styles.stepsContainer}>
          {steps.map(step => (
            <View key={step.id} style={styles.stepRow}>
              <Text style={[styles.stepIcon, {color: STATUS_COLOR[step.status]}]}>
                {STATUS_ICON[step.status]}
              </Text>
              <View style={styles.stepContent}>
                <Text style={styles.stepLabel}>{step.label}</Text>
                {step.detail && (
                  <Text
                    style={[
                      styles.stepDetail,
                      step.status === 'fail' && {color: Colors.error},
                    ]}>
                    {step.detail}
                  </Text>
                )}
              </View>
            </View>
          ))}
        </View>

        {/* Result actions */}
        {!running && (
          <View style={styles.actionsSection}>
            {allPassed && (
              <View style={styles.successBox}>
                <Text style={styles.successText}>
                  All checks passed! Connection should be working.
                </Text>
              </View>
            )}

            {firstFail?.id === 'tailscale' && (
              <TouchableOpacity
                style={styles.actionBtn}
                onPress={() => Linking.openURL('tailscale://')}
                accessibilityLabel="Open Tailscale">
                <Text style={styles.actionBtnText}>Open Tailscale App</Text>
              </TouchableOpacity>
            )}

            {firstFail?.id === 'auth' && onLoginAgain && (
              <TouchableOpacity
                style={styles.actionBtn}
                onPress={onLoginAgain}
                accessibilityLabel="Sign in again">
                <Text style={styles.actionBtnText}>Sign In Again</Text>
              </TouchableOpacity>
            )}

            <TouchableOpacity
              style={styles.retryBtn}
              onPress={runDiagnostics}
              accessibilityLabel="Run diagnostics again">
              <Text style={styles.retryText}>Run Again</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: Colors.neutral50},
  scroll: {padding: sp(4)},
  backBtn: {marginBottom: sp(2)},
  backText: {...Typography.body, color: Colors.primary},
  heading: {...Typography.h1, color: Colors.neutral900, marginBottom: sp(1)},
  subtitle: {...Typography.body, color: Colors.neutral500, marginBottom: sp(4)},
  stepsContainer: {
    backgroundColor: Colors.white,
    borderRadius: Radius.lg,
    padding: sp(4),
    marginBottom: sp(4),
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: sp(4),
  },
  stepIcon: {
    fontSize: 18,
    width: 24,
    textAlign: 'center',
    marginRight: sp(3),
    marginTop: 2,
  },
  stepContent: {flex: 1},
  stepLabel: {...Typography.body, color: Colors.neutral900},
  stepDetail: {...Typography.small, color: Colors.neutral500, marginTop: 2},
  actionsSection: {gap: sp(3)},
  successBox: {
    backgroundColor: Colors.successSurface,
    padding: sp(4),
    borderRadius: Radius.lg,
  },
  successText: {...Typography.body, color: Colors.success},
  actionBtn: {
    height: 48,
    backgroundColor: Colors.primary,
    borderRadius: Radius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  actionBtnText: {...Typography.body, color: Colors.white, fontWeight: '600'},
  retryBtn: {
    height: 48,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.neutral200,
    justifyContent: 'center',
    alignItems: 'center',
  },
  retryText: {...Typography.body, color: Colors.neutral700},
});
