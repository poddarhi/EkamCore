import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {useConnectivity} from '../contexts/ConnectivityContext';
import {Colors, Typography} from '../design-system/tokens';

const BANNER_CONFIG = {
  DEGRADED: {
    bg: Colors.warningSurface,
    text: Colors.warning,
    label: 'Slow connection',
  },
  RECONNECTING: {
    bg: Colors.warningSurface,
    text: Colors.warning,
    label: 'Reconnecting…',
  },
  DISCONNECTED_CACHED: {
    bg: Colors.errorSurface,
    text: Colors.error,
    label: 'Offline — showing cached data',
  },
  DISCONNECTED_EMPTY: {
    bg: Colors.errorSurface,
    text: Colors.error,
    label: 'Offline — no data available',
  },
  HUB_SLEEPING: {
    bg: Colors.neutral100,
    text: Colors.neutral600,
    label: 'Hub is asleep — reconnecting…',
  },
} as const;

export function ConnectivityBanner() {
  const {state} = useConnectivity();

  if (state === 'CONNECTED') return null;

  const config = BANNER_CONFIG[state as keyof typeof BANNER_CONFIG];
  if (!config) return null;

  return (
    <View
      style={[styles.banner, {backgroundColor: config.bg}]}
      accessibilityRole="alert"
      accessibilityLabel={config.label}>
      <Text style={[styles.text, {color: config.text}]}>{config.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    paddingVertical: 6,
    paddingHorizontal: 16,
    alignItems: 'center',
  },
  text: {
    ...Typography.caption,
  },
});
