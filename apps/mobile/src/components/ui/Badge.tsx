/**
 * Badge — confidence level indicator (S16-004).
 */
import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {ConfidenceBadge, Radius, Typography} from '../../design-system/tokens';

interface Props {
  level: 'high' | 'medium' | 'low';
}

export function Badge({level}: Props) {
  const theme = ConfidenceBadge[level];
  return (
    <View
      style={[styles.badge, {backgroundColor: theme.bg, borderColor: theme.border}]}
      accessibilityLabel={`${level} confidence`}>
      <Text style={[styles.text, {color: theme.text}]}>{level}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: Radius.full,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  text: {
    ...Typography.caption,
    textTransform: 'capitalize',
  },
});
