/**
 * GenericCardMobile — fallback for person, file, photo, suggestion, pack cards (S16-004).
 *
 * Renders a simple card with type label and payload title. Specific card types
 * (PersonCardMobile, etc.) will be split out as screens are built.
 */
import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import type {GenericCard} from '../../types/cards';
import {Card} from '../ui/Card';
import {Badge} from '../ui/Badge';
import {Colors, Typography, sp} from '../../design-system/tokens';

interface Props {
  card: GenericCard;
  onPress?: () => void;
}

const TYPE_LABELS: Record<string, string> = {
  person: 'Person',
  file: 'File',
  photo: 'Photo',
  suggestion: 'Suggestion',
  pack: 'Follow-up',
};

export function GenericCardMobile({card, onPress}: Props) {
  const label = TYPE_LABELS[card.type] ?? card.type;
  const title = (card.payload.title as string) ??
    (card.payload.display_name as string) ??
    (card.payload.filename as string) ??
    label;

  return (
    <Card onPress={onPress} testID={`${card.type}-card`}>
      <View style={styles.row}>
        <View style={[styles.icon, {backgroundColor: Colors.primarySurface}]}>
          <Text style={styles.iconText}>{label[0]}</Text>
        </View>
        <View style={styles.content}>
          <Text style={styles.title} numberOfLines={2}>{title}</Text>
          <Text style={styles.type}>{label}</Text>
        </View>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  row: {flexDirection: 'row', alignItems: 'center'},
  icon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: sp(3),
  },
  iconText: {...Typography.body, color: Colors.primary, fontWeight: '700'},
  content: {flex: 1},
  title: {...Typography.body, color: Colors.neutral900, fontWeight: '500'},
  type: {...Typography.caption, color: Colors.neutral500, marginTop: 2},
});
