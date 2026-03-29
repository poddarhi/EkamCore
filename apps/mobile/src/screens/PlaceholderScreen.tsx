import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {Colors, Typography, sp} from '../design-system/tokens';

interface Props {
  title: string;
}

export function PlaceholderScreen({title}: Props) {
  return (
    <View style={styles.root}>
      <Text style={styles.title} accessibilityRole="header">
        {title}
      </Text>
      <Text style={styles.subtitle}>Coming soon</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: Colors.neutral50,
    justifyContent: 'center',
    alignItems: 'center',
    padding: sp(4),
  },
  title: {
    ...Typography.h1,
    color: Colors.neutral900,
    marginBottom: sp(2),
  },
  subtitle: {
    ...Typography.body,
    color: Colors.neutral500,
  },
});
