/**
 * ReminderCardMobile — reminder card with overdue indicator (S16-004).
 */
import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import type {ReminderPayload} from '../../types/cards';
import {Card} from '../ui/Card';
import {Colors, Typography, sp} from '../../design-system/tokens';

interface Props {
  payload: ReminderPayload;
  onPress?: () => void;
}

export function ReminderCardMobile({payload, onPress}: Props) {
  const isOverdue = payload.is_overdue;

  return (
    <Card onPress={onPress} testID="reminder-card">
      <View style={styles.row}>
        <View
          style={[
            styles.checkbox,
            isOverdue && styles.checkboxOverdue,
          ]}
          accessibilityLabel={isOverdue ? 'Overdue reminder' : 'Reminder'}
        />
        <View style={styles.content}>
          <Text
            style={[styles.title, isOverdue && styles.titleOverdue]}
            numberOfLines={2}>
            {payload.title}
          </Text>
          {payload.due_at && (
            <Text style={[styles.due, isOverdue && styles.dueOverdue]}>
              {isOverdue ? 'Overdue' : new Date(payload.due_at).toLocaleDateString()}
            </Text>
          )}
          {payload.list_name && (
            <Text style={styles.meta}>{payload.list_name}</Text>
          )}
        </View>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  row: {flexDirection: 'row', alignItems: 'flex-start'},
  checkbox: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: Colors.neutral400,
    marginRight: sp(3),
    marginTop: 2,
  },
  checkboxOverdue: {borderColor: Colors.error},
  content: {flex: 1},
  title: {...Typography.body, color: Colors.neutral900},
  titleOverdue: {color: Colors.error},
  due: {...Typography.small, color: Colors.neutral500, marginTop: 2},
  dueOverdue: {color: Colors.error},
  meta: {...Typography.caption, color: Colors.neutral400, marginTop: 2},
});
