/**
 * Accessibility constants and utilities (S10-001).
 *
 * Centralizes VoiceOver labels, ARIA role mappings, and a11y helpers
 * so screens don't hardcode label strings.
 */

import type { AccessibilityRole } from 'react-native';

// ── Accessibility labels ──
// Keyed by screen/component + element for easy lookup.

export const A11yLabels = {
  // Navigation
  nav: {
    today: 'Today',
    recap: 'Recap',
    search: 'Search',
    people: 'People',
    photos: 'Photos',
    settings: 'Settings',
    goBack: 'Go back',
  },

  // Login screen
  login: {
    email: 'Email',
    password: 'Password',
    signIn: 'Sign in',
    signingIn: 'Signing in',
    errorPrefix: 'Error',
  },

  // Today screen
  today: {
    loading: 'Loading today view',
    empty: 'No items for today',
    refreshing: 'Refreshing',
  },

  // Recap screen
  recap: {
    periodDaily: 'Daily recap',
    periodWeekly: 'Weekly recap',
    loading: 'Loading recap',
    empty: 'No recap items',
  },

  // Search screen
  search: {
    input: 'Search EkamCore',
    clear: 'Clear search',
    loading: 'Searching',
    resultsCount: (n: number) => `${n} result${n !== 1 ? 's' : ''} found`,
    noResults: 'No results found',
    filterAll: 'All types filter',
    filterFiles: 'Files filter',
    filterPhotos: 'Photos filter',
    filterEvents: 'Events filter',
    filterReminders: 'Reminders filter',
    filterContacts: 'Contacts filter',
    loadMore: 'Load more results',
  },

  // Cards
  cards: {
    event: (title: string, time: string) => `Event: ${title}. ${time}`,
    reminder: (title: string, due: string | null) =>
      due ? `Reminder: ${title}. Due ${due}` : `Reminder: ${title}`,
    file: (filename: string) => `Document: ${filename}`,
    photo: (date: string | null, location: string | null) => {
      const parts = ['Photo'];
      if (date) parts.push(`taken ${date}`);
      if (location) parts.push(`at ${location}`);
      return parts.join(' ');
    },
    person: (name: string, org: string | null) =>
      org ? `${name}, ${org}` : name,
  },

  // Connectivity
  connectivity: {
    offline: "You're offline — showing cached results",
    online: 'Connected',
  },

  // Common
  common: {
    loading: 'Loading',
    retry: 'Retry',
    close: 'Close',
    dismiss: 'Dismiss',
  },
} as const;

// ── ARIA role mappings ──
// Maps component types to their React Native accessibilityRole.

export const A11yRoles: Record<string, AccessibilityRole> = {
  // Interactive
  button: 'button',
  link: 'link',
  search: 'search',
  tab: 'tab',
  switch: 'switch',
  checkbox: 'checkbox',
  radio: 'radio',
  slider: 'adjustable',

  // Content
  header: 'header',
  image: 'image',
  text: 'text',
  summary: 'summary',

  // Feedback
  alert: 'alert',
  progressbar: 'progressbar',
  timer: 'timer',

  // Navigation
  menu: 'menu',
  menuItem: 'menuitem',
  tabBar: 'tabbar',
  toolbar: 'toolbar',
};

// ── Touch target constants ──

/** Minimum touch target size in points (Apple HIG). */
export const MIN_TOUCH_TARGET = 44;

/** Default hitSlop to expand small touch targets to 44pt. */
export const DEFAULT_HIT_SLOP = {
  top: 12,
  bottom: 12,
  left: 12,
  right: 12,
} as const;

// ── Accessibility state helpers ──

/** Build accessibilityState for a toggleable element. */
export function toggleState(isOn: boolean) {
  return { checked: isOn } as const;
}

/** Build accessibilityState for a disabled element. */
export function disabledState(isDisabled: boolean) {
  return { disabled: isDisabled } as const;
}

/** Build accessibilityState for a loading element. */
export function busyState(isBusy: boolean) {
  return { busy: isBusy } as const;
}

/** Build accessibilityState for a selected element (e.g., filter chip). */
export function selectedState(isSelected: boolean) {
  return { selected: isSelected } as const;
}
