/**
 * SettingsScreen — account, hub, cache, display, about, logout (S16-007).
 */

import React, {useCallback, useEffect, useState} from 'react';
import {
  Alert,
  Linking,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {ConnectivityBanner} from '../components/ConnectivityBanner';
import {useAuth} from '../contexts/AuthContext';
import {useConnectivity} from '../contexts/ConnectivityContext';
import {cacheManager} from '../services/CacheManager';
import {apiClient} from '../api/ApiClient';
import {Colors, Radius, Typography, sp} from '../design-system/tokens';

interface Props {
  onTroubleshoot?: () => void;
}

export function SettingsScreen({onTroubleshoot}: Props) {
  const {user, logout, biometricType} = useAuth();
  const {state: connState} = useConnectivity();
  const [cacheSize, setCacheSize] = useState(0);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    cacheManager.getSize().then(setCacheSize).catch(() => {});
  }, []);

  const handleClearCache = useCallback(async () => {
    Alert.alert('Clear Cache', 'This will remove all cached data. You\'ll need an internet connection to reload.', [
      {text: 'Cancel', style: 'cancel'},
      {
        text: 'Clear',
        style: 'destructive',
        onPress: async () => {
          setClearing(true);
          await cacheManager.wipeAll();
          setCacheSize(0);
          setClearing(false);
        },
      },
    ]);
  }, []);

  const handleLogout = useCallback(async () => {
    Alert.alert('Log Out', 'You\'ll need to sign in again to access your data.', [
      {text: 'Cancel', style: 'cancel'},
      {
        text: 'Log Out',
        style: 'destructive',
        onPress: logout,
      },
    ]);
  }, [logout]);

  const handleTestConnection = useCallback(async () => {
    try {
      await apiClient.request({path: '/health', noRetry: true});
      Alert.alert('Connection OK', 'Successfully reached your EkamCore hub.');
    } catch {
      Alert.alert('Connection Failed', 'Could not reach your hub. Check Tailscale and try again.');
    }
  }, []);

  const formatBytes = (b: number) => {
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
    return `${(b / (1024 * 1024)).toFixed(1)} MB`;
  };

  const connLabel: Record<string, string> = {
    CONNECTED: 'Connected',
    DEGRADED: 'Slow connection',
    RECONNECTING: 'Reconnecting...',
    DISCONNECTED_CACHED: 'Offline (cached)',
    DISCONNECTED_EMPTY: 'Offline',
    HUB_SLEEPING: 'Hub sleeping',
  };

  const connColor: Record<string, string> = {
    CONNECTED: Colors.success,
    DEGRADED: Colors.warning,
    RECONNECTING: Colors.warning,
    DISCONNECTED_CACHED: Colors.error,
    DISCONNECTED_EMPTY: Colors.error,
    HUB_SLEEPING: Colors.neutral500,
  };

  return (
    <SafeAreaView style={styles.root}>
      <ConnectivityBanner />
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.heading} accessibilityRole="header">Settings</Text>

        {/* Account */}
        <SectionHeader title="Account" />
        <SettingsRow label="Email" value={user?.id ?? 'Not signed in'} />
        {biometricType && (
          <SettingsRow label="Biometric unlock" value={biometricType} />
        )}

        {/* Hub Connection */}
        <SectionHeader title="Hub Connection" />
        <SettingsRow
          label="Status"
          value={connLabel[connState] ?? connState}
          valueColor={connColor[connState]}
        />
        <SettingsRow label="Hub URL" value={apiClient.getBaseUrl()} />
        <SettingsButton label="Test Connection" onPress={handleTestConnection} />
        {(connState === 'DISCONNECTED_EMPTY' || connState === 'HUB_SLEEPING') && onTroubleshoot && (
          <SettingsButton label="Troubleshoot Connection" onPress={onTroubleshoot} accent />
        )}

        {/* Cache */}
        <SectionHeader title="Cache" />
        <SettingsRow label="Cache size" value={formatBytes(cacheSize)} />
        <SettingsRow label="Max size" value={formatBytes(cacheManager.getMaxSize())} />
        <SettingsButton
          label={clearing ? 'Clearing...' : 'Clear Cache'}
          onPress={handleClearCache}
          destructive
        />

        {/* About */}
        <SectionHeader title="About" />
        <SettingsRow label="App version" value="0.0.1" />
        <SettingsRow label="Platform" value="React Native" />
        <SettingsButton
          label="Open Source Licenses"
          onPress={() => Linking.openURL('https://github.com/anthropics/claude-code')}
        />

        {/* Logout */}
        <View style={styles.logoutSection}>
          <TouchableOpacity
            style={styles.logoutBtn}
            onPress={handleLogout}
            accessibilityRole="button"
            accessibilityLabel="Log out">
            <Text style={styles.logoutText}>Log Out</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────────

function SectionHeader({title}: {title: string}) {
  return (
    <Text style={styles.sectionTitle} accessibilityRole="header">
      {title}
    </Text>
  );
}

function SettingsRow({
  label,
  value,
  valueColor,
}: {
  label: string;
  value: string;
  valueColor?: string;
}) {
  return (
    <View style={styles.row} accessibilityLabel={`${label}: ${value}`}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={[styles.rowValue, valueColor ? {color: valueColor} : null]}>
        {value}
      </Text>
    </View>
  );
}

function SettingsButton({
  label,
  onPress,
  destructive,
  accent,
}: {
  label: string;
  onPress: () => void;
  destructive?: boolean;
  accent?: boolean;
}) {
  return (
    <TouchableOpacity
      style={styles.row}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}>
      <Text
        style={[
          styles.rowLabel,
          destructive && {color: Colors.error},
          accent && {color: Colors.primary, fontWeight: '600'},
        ]}>
        {label}
      </Text>
    </TouchableOpacity>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────���

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: Colors.neutral50},
  scroll: {paddingBottom: sp(16)},
  heading: {
    ...Typography.h1,
    color: Colors.neutral900,
    paddingHorizontal: sp(4),
    paddingTop: sp(4),
    paddingBottom: sp(2),
    backgroundColor: Colors.white,
    borderBottomWidth: 1,
    borderBottomColor: Colors.neutral200,
  },
  sectionTitle: {
    ...Typography.caption,
    color: Colors.neutral500,
    fontWeight: '600',
    textTransform: 'uppercase',
    paddingHorizontal: sp(4),
    paddingTop: sp(5),
    paddingBottom: sp(2),
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: sp(4),
    paddingVertical: sp(3),
    backgroundColor: Colors.white,
    borderBottomWidth: 1,
    borderBottomColor: Colors.neutral100,
    minHeight: 44,
  },
  rowLabel: {...Typography.body, color: Colors.neutral900},
  rowValue: {...Typography.body, color: Colors.neutral500},
  logoutSection: {
    paddingHorizontal: sp(4),
    paddingTop: sp(8),
  },
  logoutBtn: {
    height: 48,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.error,
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoutText: {...Typography.body, color: Colors.error, fontWeight: '600'},
});
