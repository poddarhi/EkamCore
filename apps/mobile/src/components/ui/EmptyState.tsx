/**
 * EmptyState — centered message for empty lists (S16-004).
 */
import React from 'react';
import {StyleSheet, Text, TouchableOpacity, View} from 'react-native';
import {Colors, Radius, Typography, sp} from '../../design-system/tokens';

interface Props {
  title: string;
  subtitle?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({title, subtitle, actionLabel, onAction}: Props) {
  return (
    <View style={styles.container} accessibilityRole="text">
      <Text style={styles.title}>{title}</Text>
      {subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
      {actionLabel && onAction && (
        <TouchableOpacity
          style={styles.button}
          onPress={onAction}
          accessibilityRole="button"
          accessibilityLabel={actionLabel}>
          <Text style={styles.buttonText}>{actionLabel}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: sp(8),
    minHeight: 200,
  },
  title: {...Typography.h3, color: Colors.neutral700, textAlign: 'center'},
  subtitle: {
    ...Typography.body,
    color: Colors.neutral500,
    textAlign: 'center',
    marginTop: sp(2),
  },
  button: {
    marginTop: sp(4),
    paddingHorizontal: sp(4),
    paddingVertical: sp(2),
    backgroundColor: Colors.primary,
    borderRadius: Radius.md,
  },
  buttonText: {...Typography.body, color: Colors.white, fontWeight: '600'},
});
