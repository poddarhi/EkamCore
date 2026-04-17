/**
 * EventCardMobile — calendar event card (S16-004).
 */
import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import type {EventPayload} from '../../types/cards';
import {Card} from '../ui/Card';
import {Colors, Typography, sp} from '../../design-system/tokens';

interface Props {
  payload: EventPayload;
  onPress?: () => void;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
}

export function EventCardMobile({payload, onPress}: Props) {
  const timeLabel = payload.is_all_day
    ? 'All day'
    : `${formatTime(payload.start_at)}${payload.end_at ? ` – ${formatTime(payload.end_at)}` : ''}`;

  return (
    <Card onPress={onPress} testID="event-card">
      <View style={styles.row}>
        <View style={styles.indicator} />
        <View style={styles.content}>
          <Text style={styles.title} numberOfLines={2} accessibilityRole="text">
            {payload.title}
          </Text>
          <Text style={styles.time}>{timeLabel}</Text>
          {payload.location && (
            <Text style={styles.meta} numberOfLines={1}>{payload.location}</Text>
          )}
          {payload.participants.length > 0 && (
            <Text style={styles.meta} numberOfLines={1}>
              {payload.participants.slice(0, 3).join(', ')}
              {payload.participants.length > 3 && ` +${payload.participants.length - 3}`}
            </Text>
          )}
        </View>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  row: {flexDirection: 'row', alignItems: 'flex-start'},
  indicator: {
    width: 4,
    height: '100%' as unknown as number,
    minHeight: 40,
    backgroundColor: Colors.primaryLight,
    borderRadius: 2,
    marginRight: sp(3),
  },
  content: {flex: 1},
  title: {...Typography.body, color: Colors.neutral900, fontWeight: '600'},
  time: {...Typography.small, color: Colors.primaryLight, marginTop: 2},
  meta: {...Typography.caption, color: Colors.neutral500, marginTop: 2},
});
