/**
 * CardRendererMobile — dispatches to the correct card component by type (S16-004).
 */
import React from 'react';
import type {Card} from '../types/cards';
import {EventCardMobile} from './cards/EventCardMobile';
import {ReminderCardMobile} from './cards/ReminderCardMobile';
import {StatusCardMobile} from './cards/StatusCardMobile';
import {GenericCardMobile} from './cards/GenericCardMobile';

interface Props {
  card: Card;
  onCardPress?: (card: Card) => void;
}

export function CardRendererMobile({card, onCardPress}: Props) {
  const handlePress = onCardPress ? () => onCardPress(card) : undefined;

  switch (card.type) {
    case 'event':
      return <EventCardMobile payload={card.payload} onPress={handlePress} />;
    case 'reminder':
      return <ReminderCardMobile payload={card.payload} onPress={handlePress} />;
    case 'status':
      return <StatusCardMobile payload={card.payload} />;
    default:
      return <GenericCardMobile card={card} onPress={handlePress} />;
  }
}
