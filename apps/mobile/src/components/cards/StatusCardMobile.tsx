/**
 * StatusCardMobile — greeting/status card at top of Today (S16-004).
 */
import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import type {StatusPayload} from '../../types/cards';
import {Colors, Typography, sp} from '../../design-system/tokens';

interface Props {
  payload: StatusPayload;
}

const GREETINGS: Record<string, string> = {
  morning: 'Good morning',
  afternoon: 'Good afternoon',
  evening: 'Good evening',
  night: 'Good night',
};

export function StatusCardMobile({payload}: Props) {
  const greeting = GREETINGS[payload.time_of_day] ?? 'Hello';
  return (
    <View style={styles.container} accessibilityRole="header">
      <Text style={styles.greeting}>{greeting}</Text>
      <Text style={styles.date}>
        {payload.weekday}, {new Date(payload.date).toLocaleDateString(undefined, {month: 'long', day: 'numeric'})}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: sp(4),
    paddingTop: sp(4),
    paddingBottom: sp(3),
  },
  greeting: {...Typography.h1, color: Colors.neutral900},
  date: {...Typography.body, color: Colors.neutral500, marginTop: 2},
});
