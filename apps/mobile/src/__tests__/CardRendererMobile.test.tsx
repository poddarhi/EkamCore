import React from 'react';
import {render, screen} from '@testing-library/react-native';
import {CardRendererMobile} from '../components/CardRendererMobile';
import type {Card, EventCard, ReminderCard, StatusCard, GenericCard} from '../types/cards';

describe('CardRendererMobile', () => {
  it('renders EventCardMobile for event type', () => {
    const card: EventCard = {
      id: 'e1',
      type: 'event',
      priority_score: 0.9,
      source_ids: [],
      payload: {
        title: 'Team Standup',
        start_at: '2026-04-17T09:00:00Z',
        end_at: '2026-04-17T09:30:00Z',
        is_all_day: false,
        location: 'Zoom',
        calendar_name: 'Work',
        participants: ['Alice', 'Bob'],
      },
    };

    render(<CardRendererMobile card={card} />);
    expect(screen.getByTestID('event-card')).toBeTruthy();
  });

  it('renders ReminderCardMobile for reminder type', () => {
    const card: ReminderCard = {
      id: 'r1',
      type: 'reminder',
      priority_score: 0.8,
      source_ids: [],
      payload: {
        title: 'Buy groceries',
        due_at: '2026-04-17T18:00:00Z',
        priority: 'medium',
        list_name: 'Personal',
        notes: null,
        is_overdue: false,
      },
    };

    render(<CardRendererMobile card={card} />);
    expect(screen.getByTestID('reminder-card')).toBeTruthy();
  });

  it('renders GenericCardMobile for person type', () => {
    const card: GenericCard = {
      id: 'p1',
      type: 'person',
      priority_score: 0.7,
      source_ids: [],
      payload: {display_name: 'Alice Smith'},
    };

    render(<CardRendererMobile card={card} />);
    expect(screen.getByTestID('person-card')).toBeTruthy();
  });

  it('renders GenericCardMobile for pack type', () => {
    const card: GenericCard = {
      id: 'pk1',
      type: 'pack',
      priority_score: 0.6,
      source_ids: [],
      payload: {title: 'Follow up with Bob'},
    };

    render(<CardRendererMobile card={card} />);
    expect(screen.getByTestID('pack-card')).toBeTruthy();
  });
});
