/**
 * FilterChip — tappable filter pill (S16-005).
 */
import React from 'react';
import {StyleSheet, Text, TouchableOpacity} from 'react-native';
import {Colors, Radius, Typography, sp} from '../../design-system/tokens';

interface Props {
  label: string;
  selected: boolean;
  onPress: () => void;
}

export function FilterChip({label, selected, onPress}: Props) {
  return (
    <TouchableOpacity
      style={[styles.chip, selected && styles.chipSelected]}
      onPress={onPress}
      accessibilityRole="tab"
      accessibilityState={{selected}}
      accessibilityLabel={label}>
      <Text style={[styles.text, selected && styles.textSelected]}>
        {label}
      </Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  chip: {
    paddingHorizontal: sp(3),
    paddingVertical: sp(1),
    borderRadius: Radius.full,
    backgroundColor: Colors.neutral100,
    marginRight: sp(2),
  },
  chipSelected: {
    backgroundColor: Colors.primary,
  },
  text: {
    ...Typography.caption,
    color: Colors.neutral600,
  },
  textSelected: {
    color: Colors.white,
  },
});
